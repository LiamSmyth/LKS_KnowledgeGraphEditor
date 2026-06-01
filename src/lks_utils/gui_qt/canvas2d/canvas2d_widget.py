"""`Canvas2DWidget`: a reusable Qt widget hosting a 2-D scene of `CanvasItem`s.

``Canvas2D`` is the public alias kept for backward compatibility.

This is the **foundation widget** for the painter, node graphs, and
any future tool that needs an unbounded 2-D viewport with pan/zoom/
rotation. It knows nothing about tiles, brushes, or pixels.

Internally the widget delegates to three extracted components:

* :class:`~lks_utils.gui_qt.canvas2d.scene2d.Scene2D` — item/overlay
  data model, dirty tracking, spatial queries.
* :class:`~lks_utils.gui_qt.canvas2d.camera2d.Camera2D` — view state
  and animated navigation.
* :class:`~lks_utils.gui_qt.canvas2d.canvas2d_renderer.Canvas2DRenderer`
  — stateless paint orchestration.

All three are public attributes (``canvas.scene``, ``canvas.camera``,
``canvas.renderer``) so advanced callers can share a scene between
multiple widgets or drive the camera from outside the widget.

Design notes / deviations from the spec:

* The foundation uses a plain ``QWidget`` with ``QPainter`` rather than
  ``QOpenGLWidget`` + ModernGL. ``QPainter`` gives items a simple,
  hardware-accelerated drawing surface and lets the foundation be
  testable without a GPU. A future GPU-backed subclass can swap in
  ``QOpenGLWidget`` for items that need raw GL textures (e.g. the
  TileTree renderer).
* World-space drawing is provided by setting the painter's transform
  to the view's world->screen affine before each item paints. Items
  draw in world coordinates; the transform handles pan/zoom/rotation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    QRectF,
    QSize,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFocusEvent,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QTabletEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QToolTip, QWidget

from lks_utils.gui_qt.canvas2d.actions import (
    CANVAS_DELETE_SELECTED,
    CANVAS_DESELECT_ALL,
    CANVAS_FIT_CONTENT,
    CANVAS_PAN,
    CANVAS_PRIMARY,
    CANVAS_REDO,
    CANVAS_RESET_VIEW,
    CANVAS_RESET_ZOOM,
    CANVAS_ROTATE,
    CANVAS_SELECT_ALL,
    CANVAS_SECONDARY,
    CANVAS_UNDO,
    CANVAS_ZOOM_IN,
    CANVAS_ZOOM_OUT,
    CANVAS_COPY,
    CANVAS_CUT,
    CANVAS_PASTE,
)
from lks_utils.gui_qt.canvas2d.commands.add_item_command import AddItemCommand
from lks_utils.gui_qt.canvas2d.commands.move_items_command import MoveItemsCommand
from lks_utils.gui_qt.canvas2d.commands.remove_item_command import RemoveItemCommand
from lks_utils.gui_qt.canvas2d.overlays.rubber_band_overlay import RubberBandOverlay
from lks_utils.gui_qt.canvas2d.overlays.selection_overlay import SelectionOverlay
from lks_utils.gui_qt.canvas2d.canvas2d_capabilities import Canvas2DCapabilities
from lks_utils.gui_qt.canvas2d.command_history import CommandHistory
from lks_utils.gui_qt.canvas2d.camera2d import Camera2D
from lks_utils.gui_qt.canvas2d.canvas2d_renderer import Canvas2DRenderer
from lks_utils.gui_qt.canvas2d.canvas_document import (
    CanvasDocument,
    _view_from_dict,
    _view_to_dict,
)
from lks_utils.gui_qt.canvas2d.canvas_input_event import (
    CANVAS_ITEM_KEY,
    CANVAS_ITEM_WHEEL,
    CANVAS_MOVE,
    CanvasInputEvent,
)
from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem
from lks_utils.gui_qt.canvas2d.canvas_item_registry import get_canvas_item_type
from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.image_canvas_item import IMAGE_EXTENSIONS, ImageCanvasItem
from lks_utils.gui_qt.canvas2d.scene2d import Scene2D
from lks_utils.gui_qt.canvas2d.view_transform import ViewTransform
from lks_utils.gui_qt.canvas2d.viewport_overlay import ViewportOverlay
from lks_utils.gui_qt.qt_paint_profile_mixin import QtPaintProfileMixin
from lks_utils.input import GestureKind, Modifier, MouseButton, get_default_bindings
from lks_utils.input.qt_adapter import (
    qt_button_to_logical,
    qt_modifiers_to_logical,
    wheel_event_pair,
)
from lks_utils.spatial.aabb import AABB

if TYPE_CHECKING:
    from pathlib import Path


class _CanvasHoverTooltipPopup(QWidget):
    """Small mouse-transparent popup used for canvas hover tooltips."""

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._label = QWidget(self)
        from PySide6.QtWidgets import QLabel, QVBoxLayout

        self._text_label = QLabel(self)
        self._text_label.setWordWrap(True)
        self._text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._text_label)

        self._apply_palette_style()
        self.hide()

    def _apply_palette_style(self) -> None:
        palette = self.palette()
        bg = palette.toolTipBase().color().name()
        fg = palette.toolTipText().color().name()
        border = palette.mid().color().name()
        self.setStyleSheet(
            "QWidget {"
            f"background: {bg};"
            f"color: {fg};"
            f"border: 1px solid {border};"
            "border-radius: 0;"
            "}"
        )
        self._text_label.setStyleSheet(
            "QLabel { padding: 4px 6px; border: none; background: transparent; }"
        )

    def show_text(self, global_pos: QPoint, text: str) -> None:
        self._apply_palette_style()
        self._text_label.setText(text)
        self._text_label.adjustSize()
        self.adjustSize()

        anchor = QPoint(global_pos.x() + 16, global_pos.y() + 20)
        screen = QGuiApplication.screenAt(global_pos)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            x = min(anchor.x(), available.right() - self.width())
            y = min(anchor.y(), available.bottom() - self.height())
            anchor = QPoint(max(available.left(), x), max(available.top(), y))
        self.move(anchor)
        self.show()
        self.raise_()


class Canvas2DWidget(QtPaintProfileMixin, QWidget):
    """A 2-D viewport widget hosting `CanvasItem`s and overlays.

    Pan / zoom / rotate, item placement, dirty tracking, and built-in
    overlays. Add items via :meth:`add_item`, overlays via
    :meth:`add_overlay`. The current `ViewTransform` is available via
    :meth:`view`; replace it via :meth:`set_view`.

    The widget owns three public sub-components:

    * **scene** (:class:`~lks_utils.gui_qt.canvas2d.scene2d.Scene2D`):
      items, overlays, dirty tracker.
    * **camera** (:class:`~lks_utils.gui_qt.canvas2d.camera2d.Camera2D`):
      view state, animated navigation, bookmarks.
    * **renderer** (:class:`~lks_utils.gui_qt.canvas2d.canvas2d_renderer.Canvas2DRenderer`):
      stateless paint orchestration.

    Signals:
        view_changed(ViewTransform): View transform changed.
        item_added(CanvasItem)
        item_removed(CanvasItem)
        item_changed(CanvasItem, object): An item requested a repaint
            (e.g. moved, resized, restyled). Second arg is the dirty
            world AABB (or ``None`` for "whole item"). Useful for
            companion widgets like the minimap that need to refresh
            on item edits, not just on add/remove.
        cursor_world_pos(float, float): Last hovered world position.
            Useful for HUDs.
    """

    view_changed = Signal(object)       # ViewTransform
    item_added = Signal(object)           # CanvasItem
    item_removed = Signal(object)         # CanvasItem
    item_changed = Signal(object, object)  # CanvasItem, AABB | None
    cursor_world_pos = Signal(float, float)
    #: Re-exported from :attr:`scene`'s owned ``SelectionModel``.
    selection_changed = Signal()
    #: Fires when active selected item changes.
    active_selection_changed = Signal(object)
    #: Fires with the new ``is_modified`` value when dirty state changes.
    modified_changed = Signal(bool)
    #: Emitted after a widget-managed item drag is committed to history.
    items_moved = Signal(list)

    _MIN_ZOOM: float = 1.0 / 64.0
    _MAX_ZOOM: float = 256.0
    _ZOOM_STEP: float = 1.25
    _ROTATION_SNAP_DEG: float = 15.0  # snap to nearest 90° if within this
    _HOVER_TOOLTIP_DELAY_MS: int = 350

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        capabilities: Canvas2DCapabilities | None = None,
        scene: Scene2D | None = None,
        camera: Camera2D | None = None,
    ) -> None:
        super().__init__(parent)

        self.capabilities: Canvas2DCapabilities = (
            capabilities if capabilities is not None else Canvas2DCapabilities()
        )

        # Public sub-components — may be shared across multiple widgets.
        self.scene: Scene2D = scene if scene is not None else Scene2D(self)
        self.camera: Camera2D = camera if camera is not None else Camera2D(
            self)
        self.renderer: Canvas2DRenderer = Canvas2DRenderer()

        # Drag state (None when no drag in flight).
        self._drag_action: str | None = None
        self._drag_screen_anchor: tuple[float, float] | None = None
        self._drag_view_anchor: ViewTransform | None = None
        self._drag_world_anchor: tuple[float, float] | None = None
        self._drag_rotate_reference_angle: float | None = None
        # Item that's actively consuming a primary drag (so we keep
        # routing drag/release to it even when cursor leaves its bounds).
        self._primary_item: CanvasItem | None = None
        # Item that owns keyboard input focus for synthetic canvas-key
        # forwarding (used by offscreen adapters like pixmap-backed widgets).
        self._key_input_item: CanvasItem | None = None

        # Rubber-band drag state.
        self._rubber_band_overlay: RubberBandOverlay | None = None
        self._rubber_band_screen_start: tuple[float, float] | None = None
        self._rubber_band_subtractive: bool = False
        self._rubber_band_mouse_grabbed: bool = False

        # Clipboard state.
        # item_clone_fn must be set by the owner to enable paste.
        # Signature: (item: CanvasItem) -> CanvasItem | None
        from typing import Callable
        self.item_clone_fn: Callable[[CanvasItem],
                                     CanvasItem | None] | None = None
        self._clipboard: list[CanvasItem] = []
        self._paste_offset: tuple[float, float] = (20.0, 20.0)

        # Widget-managed item drag state.
        self._dragging_items: list[CanvasItem] = []
        self._item_drag_screen_prev: tuple[float, float] | None = None
        self._item_drag_world_deltas: dict[int, tuple[float, float]] = {}

        # Last cursor screen pos (None = not over widget).
        self._cursor_screen: tuple[float, float] | None = None
        self._hover_tooltip_popup = _CanvasHoverTooltipPopup()
        self._hover_tooltip_timer = QTimer(self)
        self._hover_tooltip_timer.setSingleShot(True)
        self._hover_tooltip_timer.timeout.connect(self._show_hover_tooltip)
        self._hover_tooltip_item: CanvasItem | None = None
        self._hover_tooltip_text: str | None = None
        self._pending_hover_tooltip_item: CanvasItem | None = None
        self._pending_hover_tooltip_text: str | None = None
        self._pending_hover_tooltip_global_pos: QPoint | None = None

        self.history: CommandHistory | None = (
            self.create_command_history()
            if self.capabilities.allow_undo_redo
            else None
        )

        # Per-action smoothing alpha (fraction of remaining distance
        # consumed each 16 ms tick). Higher = snappier, lower = floatier.
        self._zoom_alpha: float = 0.35
        self._pan_alpha: float = 0.5

        # Wire camera → widget.
        self.camera.view_changed.connect(self._on_camera_view_changed)
        self._is_modified: bool = False

        # Wire scene → widget.
        self.scene.item_added.connect(self._on_scene_item_added)
        self.scene.item_removed.connect(self._on_scene_item_removed)
        self.scene.item_changed.connect(self._on_scene_item_changed)
        self.scene.dirty_changed.connect(self.update)
        self.scene.selection_changed.connect(self.selection_changed)
        self.scene.active_selection_changed.connect(
            self.active_selection_changed)

        # Selection handles overlay (auto-enabled when selection is supported).
        if self.capabilities.allow_selection:
            self._selection_overlay: SelectionOverlay | None = SelectionOverlay(
                self.scene.selection()
            )
            self.add_overlay(self._selection_overlay)
        else:
            self._selection_overlay = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TabletTracking, True)
        self.setAcceptDrops(True)

    # ------------------------------------------------------------------ #
    # Camera / scene signal forwarders                                     #
    # ------------------------------------------------------------------ #

    def _on_camera_view_changed(self, view: ViewTransform) -> None:
        for it in self.scene.items():
            it.on_view_changed(view)
        for ov in self.scene.overlays():
            ov.on_view_changed(view)
        self.view_changed.emit(view)
        self.update()

    def _on_scene_item_added(self, item: CanvasItem) -> None:
        self.item_added.emit(item)
        self._set_modified(True)

    def _on_scene_item_removed(self, item: CanvasItem) -> None:
        if self._primary_item is item:
            self._primary_item = None
        if self._key_input_item is item:
            self._key_input_item = None
        self.item_removed.emit(item)
        self._set_modified(True)

    def _on_scene_item_changed(self, item: CanvasItem, region: object) -> None:
        self.item_changed.emit(item, region)
        # Only mark modified when the item opts into persistence.
        if item.to_dict() is not None:
            self._set_modified(True)
        self.update()

    def _set_modified(self, value: bool) -> None:
        if self._is_modified != value:
            self._is_modified = value
            self.modified_changed.emit(value)

    # ------------------------------------------------------------------ #
    # HasInputScope                                                        #
    # ------------------------------------------------------------------ #

    def create_command_history(self) -> CommandHistory:
        """Factory hook for command history implementations."""
        return CommandHistory(self)

    def input_scope(self) -> str | None:
        """Return the active input scope for this canvas widget."""
        return "canvas2d"

    # ------------------------------------------------------------------ #
    # Item / overlay management (delegates to Scene2D)                    #
    # ------------------------------------------------------------------ #

    def add_item(self, item: CanvasItem, z_order: int | None = None) -> None:
        self.scene.add_item(item, z_order)

    def remove_item(self, item: CanvasItem) -> None:
        self.scene.remove_item(item)

    def items(self) -> list[CanvasItem]:
        return self.scene.items()

    def add_overlay(self, overlay: ViewportOverlay) -> None:
        self.scene.add_overlay(overlay)

    def remove_overlay(self, overlay: ViewportOverlay) -> None:
        self.scene.remove_overlay(overlay)

    def overlays(self) -> list[ViewportOverlay]:
        return self.scene.overlays()

    def enable_debug_bounds(self, *, show_labels: bool = True) -> None:
        """Attach a :class:`~lks_utils.gui_qt.canvas2d.debug.canvas_bounds_overlay.CanvasBoundsOverlay`.

        Draws 1px red AABBs around every scene item in screen space.
        Idempotent — calling more than once adds only one overlay.
        """
        from lks_utils.gui_qt.canvas2d.debug.canvas_bounds_overlay import CanvasBoundsOverlay

        for ov in self.scene.overlays():
            if isinstance(ov, CanvasBoundsOverlay):
                return  # already installed
        self.scene.add_overlay(CanvasBoundsOverlay(
            self.scene, show_labels=show_labels))

    def register_hud_provider(self, callback: Callable[[], str]) -> None:
        """Register a string-returning callback for verbose HUD overlays."""
        self.scene.register_hud_provider(callback)

    def hud_strings(self) -> list[str]:
        """All registered HUD provider strings (overlay-friendly)."""
        return self.scene.hud_strings()

    # ------------------------------------------------------------------ #
    # Selection (delegates to Scene2D → SelectionModel)                   #
    # ------------------------------------------------------------------ #

    def select_item(self, item: CanvasItem, *, additive: bool = False) -> None:
        """Select *item* (see :meth:`~Scene2D.select_item`)."""
        self.scene.select_item(item, additive=additive)
        if self.capabilities.bring_selected_to_front:
            self.scene.bring_item_to_front(item)

    def toggle_item_selection(self, item: CanvasItem) -> None:
        """Toggle *item* in the current selection set."""
        self.scene.toggle_item_selection(item)
        active = self.scene.active_selected_item()
        if self.capabilities.bring_selected_to_front and active is not None:
            self.scene.bring_item_to_front(active)

    def select_range_to_item(self, item: CanvasItem, *, additive: bool = False) -> None:
        """Select anchor-to-item range using scene order."""
        self.scene.select_range_to(item, additive=additive)
        active = self.scene.active_selected_item()
        if self.capabilities.bring_selected_to_front and active is not None:
            self.scene.bring_item_to_front(active)

    def deselect_item(self, item: CanvasItem) -> None:
        """Remove *item* from the selection."""
        self.scene.deselect_item(item)

    def clear_selection(self) -> None:
        """Clear the selection."""
        self.scene.clear_selection()

    def selected_items(self) -> list[CanvasItem]:
        """Return a snapshot of the current selection."""
        return self.scene.selected_items()

    def active_selected_item(self) -> CanvasItem | None:
        """Return the active selected item, if any."""
        return self.scene.active_selected_item()

    # ------------------------------------------------------------------ #
    # Modified / dirty state                                              #
    # ------------------------------------------------------------------ #

    @property
    def is_modified(self) -> bool:
        """``True`` iff the canvas has unsaved changes."""
        return self._is_modified

    def mark_saved(self) -> None:
        """Reset the modified flag (e.g. after a successful save)."""
        self._set_modified(False)

    # ------------------------------------------------------------------ #
    # View management (delegates to Camera2D)                             #
    # ------------------------------------------------------------------ #

    def view(self) -> ViewTransform:
        return self.camera.view()

    def set_view(self, view: ViewTransform) -> None:
        self.camera.set_view(view)

    # Default duration for animated go-to. Constant-time so every
    # transition feels equally snappy regardless of distance.
    GOTO_DURATION_MS: int = 220

    def reset_view(self, *, animate: bool = False) -> None:
        self.camera.reset_view(animate=animate)

    def reset_zoom(self, *, animate: bool = False) -> None:
        self.camera.reset_zoom(animate=animate)

    def fit_to_aabb(
        self,
        aabb: AABB,
        buffer_world_px: float = 0.0,
        *,
        animate: bool = False,
    ) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        self.camera.fit_to_aabb(
            aabb,
            (float(self.width()), float(self.height())),
            buffer_world_px,
            animate=animate,
        )

    def fit_to_content(
        self, buffer_world_px: float = 64.0, *, animate: bool = False,
    ) -> None:
        self.frame_all(buffer_world_px=buffer_world_px, animate=animate)

    def frame_all(
        self,
        buffer_world_px: float = 64.0,
        *,
        animate: bool = False,
        bounds: AABB | None = None,
    ) -> bool:
        """Frame all visible content (or explicit ``bounds``) in the viewport.

        Returns ``True`` when a concrete bounds fit was applied, ``False`` when
        no bounds were available and the view was reset instead.
        """
        target = bounds if bounds is not None else self.scene.union_bounds()
        if target is None:
            self.camera.reset_view(animate=animate)
            return False
        self.fit_to_aabb(
            target, buffer_world_px=buffer_world_px, animate=animate)
        return True

    def go_to(
        self,
        target: ViewTransform,
        *,
        animate: bool = True,
        duration_ms: int | None = None,
    ) -> None:
        """Canonical "go to view" command — delegates to :attr:`camera`."""
        self.camera.go_to(target, animate=animate, duration_ms=duration_ms)

    def cancel_view_animation(self) -> None:
        """Stop any in-flight view animation — delegates to :attr:`camera`."""
        self.camera.cancel_view_animation()

    def is_view_animating(self) -> bool:
        """True iff a ``go_to`` or smoothing-pump animation is running."""
        return self.camera.is_view_animating()

    def fly_to(self, target: ViewTransform, duration_ms: int = 250) -> None:
        """Back-compat shim — delegates to :meth:`go_to`."""
        self.camera.fly_to(target, duration_ms=duration_ms)

    # Bookmark API (thin forwarding layer to camera.)
    def save_view(self, name: str) -> None:
        self.camera.save_view(name)

    def restore_view(self, name: str, *, animate: bool = True) -> None:
        self.camera.restore_view(name, animate=animate)

    def delete_bookmark(self, name: str) -> None:
        self.camera.delete_bookmark(name)

    def bookmarks(self) -> dict[str, ViewTransform]:
        """Return a copy of the stored bookmarks mapping name → :class:`ViewTransform`."""
        return self.camera.bookmarks()

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def to_document(self) -> CanvasDocument:
        """Capture current canvas state as a frozen :class:`CanvasDocument`."""
        view_dict = _view_to_dict(self.camera.view())

        items_data: list[dict] = []
        for item in self.scene.items():
            d = item.to_dict()
            if d is not None:
                items_data.append(d)

        overlays_data: list[dict] = []
        for ov in self.scene.overlays():
            d = ov.to_dict()
            if d is not None:
                overlays_data.append(d)

        bookmarks_data: dict[str, dict] = {
            name: _view_to_dict(vt)
            for name, vt in self.camera.bookmarks().items()
        }

        return CanvasDocument(
            version=1,
            view=view_dict,
            items=items_data,
            overlays=overlays_data,
            bookmarks=bookmarks_data,
        )

    def load_document(
        self,
        doc: CanvasDocument,
        *,
        restore_view: bool = True,
    ) -> None:
        """Restore canvas state from a :class:`CanvasDocument`.

        Clears the current scene, reconstructs items and overlays via the
        type registry, installs bookmarks, and optionally restores the view.

        Args:
            doc:          The document to load.
            restore_view: When ``True`` (default) the view is set to the
                          saved position instantly (no animation).
        """
        # Clear existing items (selection is cleaned up automatically by
        # Scene2D.remove_item).
        for item in list(self.scene.items()):
            self.scene.remove_item(item)
        for ov in list(self.scene.overlays()):
            self.scene.remove_overlay(ov)

        # Reconstruct items.
        for item_dict in doc.items:
            type_name = item_dict.get("type", "")
            cls = get_canvas_item_type(type_name)
            if cls is None:
                continue  # unknown type — skip silently
            try:
                item = cls.from_dict(item_dict)
            except Exception:  # noqa: BLE001
                continue
            self.scene.add_item(item)

        # Reconstruct overlays.
        for ov_dict in doc.overlays:
            type_name = ov_dict.get("type", "")
            cls = get_canvas_item_type(type_name)
            if cls is None:
                continue
            try:
                ov = cls.from_dict(ov_dict)
            except Exception:  # noqa: BLE001
                continue
            self.scene.add_overlay(ov)

        # Restore bookmarks.
        for name, vt_dict in doc.bookmarks.items():
            vt = _view_from_dict(vt_dict)
            self.camera._bookmarks[name] = vt  # noqa: SLF001

        # Restore view.
        if restore_view and doc.view:
            vt = _view_from_dict(doc.view)
            self.camera.set_view(vt)

        # After loading, the canvas reflects the file → not modified.
        self._set_modified(False)

    def save_json(self, path: Path | str) -> None:  # noqa: ANN001
        """Save the canvas document to a JSON file.

        Uses atomic write (``*.tmp`` → rename) for crash safety.
        """
        import json
        from pathlib import Path as _Path
        from lks_utils.core import atomic_write
        p = _Path(path)
        doc = self.to_document()
        data = json.dumps(doc.to_dict(), indent=2)
        atomic_write(p, data, encoding="utf-8")
        self._set_modified(False)

    def load_json(self, path: Path | str) -> None:  # noqa: ANN001
        """Load a canvas document from a JSON file."""
        import json
        from pathlib import Path as _Path
        p = _Path(path)
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        doc = CanvasDocument.from_dict(data)
        self.load_document(doc)

    # ------------------------------------------------------------------ #
    # Painting (delegated to Canvas2DRenderer)                            #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.renderer.paint(self.scene, self.camera, painter, self.rect())
        painter.end()
        # Outer scope timing and timings.total_ms patch handled by
        # QtPaintProfileMixin — no manual perf_counter boilerplate needed.

    # ------------------------------------------------------------------ #
    # Resize                                                               #
    # ------------------------------------------------------------------ #

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.scene.dirty_tracker().mark(None)
        super().resizeEvent(event)

    # ------------------------------------------------------------------ #
    # Input → action dispatch                                              #
    # ------------------------------------------------------------------ #

    def _screen_to_world(
        self, sx: float, sy: float
    ) -> tuple[float, float]:
        return self.camera.view().screen_to_world(
            (sx, sy), (float(self.width()), float(self.height()))
        )

    def _make_event(
        self,
        action,
        phase: str,
        screen_pos: tuple[float, float],
        modifiers,
        delta: tuple[float, float] | None = None,
        pressure: float = 1.0,
        tilt: tuple[float, float] = (0.0, 0.0),
        is_tablet: bool = False,
    ) -> CanvasInputEvent:
        wp = self._screen_to_world(*screen_pos)
        return CanvasInputEvent(
            action=action,
            phase=phase,  # type: ignore[arg-type]
            world_pos=wp,
            screen_pos=screen_pos,
            pressure=pressure,
            tilt=tilt,
            modifiers=modifiers,
            delta=delta,
            is_tablet=is_tablet,
        )

    def _route_to_topmost(
        self, world_pos: tuple[float, float], event: CanvasInputEvent
    ) -> CanvasItem | None:
        """Walk items top-down; first to consume wins."""
        for item in reversed(self.scene.items()):
            if not item.hit_test(world_pos):
                continue
            if item.handle_input(event):
                return item
        return None

    def _topmost_hit_item(self, world_pos: tuple[float, float]) -> CanvasItem | None:
        """Return the topmost item whose precise hit-test contains *world_pos*."""
        for item in reversed(self.scene.items()):
            if item.hit_test(world_pos):
                return item
        return None

    def _clear_hover_tooltip(self) -> None:
        if self._hover_tooltip_text is None and self._pending_hover_tooltip_text is None:
            return
        self._hover_tooltip_timer.stop()
        self._hover_tooltip_popup.hide()
        self._hover_tooltip_item = None
        self._hover_tooltip_text = None
        self._pending_hover_tooltip_item = None
        self._pending_hover_tooltip_text = None
        self._pending_hover_tooltip_global_pos = None

    def _show_hover_tooltip(self) -> None:
        if self._pending_hover_tooltip_text is None or self._pending_hover_tooltip_global_pos is None:
            return
        self._hover_tooltip_popup.show_text(
            self._pending_hover_tooltip_global_pos,
            self._pending_hover_tooltip_text,
        )
        self._hover_tooltip_item = self._pending_hover_tooltip_item
        self._hover_tooltip_text = self._pending_hover_tooltip_text

    def _update_hover_tooltip(
        self,
        screen_pos: tuple[float, float],
        world_pos: tuple[float, float],
    ) -> None:
        hit = self._topmost_hit_item(world_pos)
        tooltip_text: str | None = None
        if hit is not None:
            raw = hit.tooltip_at(world_pos)
            if raw is not None:
                stripped = raw.strip()
                if stripped:
                    tooltip_text = stripped

        if hit is self._hover_tooltip_item and tooltip_text == self._hover_tooltip_text:
            return

        global_pos = self.mapToGlobal(
            QPoint(int(round(screen_pos[0])), int(round(screen_pos[1])))
        )

        if (
            hit is self._pending_hover_tooltip_item
            and tooltip_text == self._pending_hover_tooltip_text
        ):
            self._pending_hover_tooltip_global_pos = global_pos
            return

        if tooltip_text is None:
            self._clear_hover_tooltip()
            return

        self._hover_tooltip_popup.hide()
        self._hover_tooltip_item = None
        self._hover_tooltip_text = None
        self._pending_hover_tooltip_item = hit
        self._pending_hover_tooltip_text = tooltip_text
        self._pending_hover_tooltip_global_pos = global_pos
        self._hover_tooltip_timer.start(self._HOVER_TOOLTIP_DELAY_MS)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._clear_hover_tooltip()
        button = qt_button_to_logical(event.button())
        if button is None:
            return super().mousePressEvent(event)
        mods = qt_modifiers_to_logical(event.modifiers())
        screen = (event.position().x(), event.position().y())
        bindings = get_default_bindings()

        # View gestures take priority over CANVAS_PRIMARY when explicitly
        # bound (e.g. middle-drag for pan).
        if bindings.matches_mouse(CANVAS_PAN.id, button, mods, GestureKind.DRAG):
            if self.camera.is_locked:
                event.accept()
                return
            self._begin_drag(CANVAS_PAN.id, screen)
            event.accept()
            return
        if bindings.matches_mouse(CANVAS_ROTATE.id, button, mods, GestureKind.DRAG):
            if self.camera.is_locked:
                event.accept()
                return
            self._begin_drag(CANVAS_ROTATE.id, screen)
            event.accept()
            return

        # Primary press → topmost item.
        # Also enter this block when the same primary button is used with
        # common multi-select modifiers (Shift/Ctrl) so that additive,
        # toggle, and range-select clicks are handled here rather than
        # silently falling through.
        _primary_btn_only = bindings.matches_mouse(
            CANVAS_PRIMARY.id, button, frozenset(), GestureKind.PRESS
        )
        _multi_select_mods = frozenset({Modifier.SHIFT, Modifier.CTRL})
        if bindings.matches_mouse(
            CANVAS_PRIMARY.id, button, mods, GestureKind.PRESS
        ) or (_primary_btn_only and not (mods - _multi_select_mods)):
            wp = self._screen_to_world(*screen)
            ev = self._make_event(CANVAS_PRIMARY, "press", screen, mods)
            consumer = self._route_to_topmost(wp, ev)
            if consumer is not None:
                # Let item-local interaction (e.g. embedded widget fields,
                # sliders, buttons) win over canvas-level selection.
                self._primary_item = consumer
                self._key_input_item = consumer
                event.accept()
                return

            hit = self._topmost_hit_item(wp)
            is_shift = Modifier.SHIFT in mods
            is_ctrl = Modifier.CTRL in mods

            if self.capabilities.allow_selection:
                if hit is None:
                    self._key_input_item = None
                    if not is_shift and not is_ctrl:
                        self.clear_selection()
                    # Empty-space drag uses modifier policy:
                    # plain -> replace, shift -> additive, ctrl -> subtractive.
                    self._begin_rubber_band(screen, subtractive=is_ctrl)
                    event.accept()
                    return
                if hit.selectable:
                    if not self.capabilities.allow_multi_select:
                        if is_shift or is_ctrl:
                            # Modifier+click on a canvas item toggles it
                            # in/out of selection even when
                            # allow_multi_select is off (legacy behavior).
                            self.toggle_item_selection(hit)
                        elif not self.scene.selection().is_selected(hit):
                            # Plain click on an *unselected* item → replace.
                            # Plain click on an *already-selected* item →
                            # keep the current selection so a multi-drag can
                            # start without clearing it first.
                            self.select_item(hit, additive=False)
                    else:
                        if is_ctrl:
                            self.toggle_item_selection(hit)
                        elif is_shift:
                            # Shift-click is add-only for canvas semantics.
                            self.select_item(hit, additive=True)
                        else:
                            self.select_item(hit, additive=False)

            if (
                self.capabilities.allow_selection
                and self.capabilities.allow_drag
                and hit is not None
                and hit.draggable
            ):
                dragged_items = [hit]
                if self.scene.selection().is_selected(hit):
                    dragged_items = [
                        item
                        for item in self.selected_items()
                        if item.draggable
                    ]
                    if not dragged_items:
                        dragged_items = [hit]
                self._begin_item_drag(dragged_items, screen)
                event.accept()
                return
            # Fallthrough: nothing consumed → fall back to view actions
            # if a view binding matches LMB-press (rare; left empty here).

        # Secondary press → topmost item.
        if bindings.matches_mouse(
            CANVAS_SECONDARY.id, button, mods, GestureKind.PRESS
        ):
            wp = self._screen_to_world(*screen)
            ev = self._make_event(CANVAS_SECONDARY, "press", screen, mods)
            self._route_to_topmost(wp, ev)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        screen = (event.position().x(), event.position().y())
        self._cursor_screen = screen
        wp = self._screen_to_world(*screen)
        self.cursor_world_pos.emit(wp[0], wp[1])

        # Active drag?
        if self._drag_action is not None and self._drag_screen_anchor is not None:
            self._clear_hover_tooltip()
            self._handle_drag_motion(screen)
            event.accept()
            return

        # Active primary item drag?
        if self._primary_item is not None:
            self._clear_hover_tooltip()
            mods = qt_modifiers_to_logical(event.modifiers())
            ev = self._make_event(CANVAS_PRIMARY, "drag", screen, mods)
            self._primary_item.handle_input(ev)
            event.accept()
            return

        # Widget-managed item drag.
        if self._dragging_items:
            self._clear_hover_tooltip()
            self._handle_item_drag_motion(screen)
            event.accept()
            return

        # Rubber-band drag.
        if self._rubber_band_overlay is not None:
            self._clear_hover_tooltip()
            self._rubber_band_overlay.update_rect(*screen)
            self.update()
            event.accept()
            return

        # Plain hover-move event for items that care.
        mods = qt_modifiers_to_logical(event.modifiers())
        ev = self._make_event(CANVAS_MOVE, "move", screen, mods)
        # Hover events: don't re-route per-item; we leave that to specific
        # consumers via `cursor_world_pos`. Items can subscribe to that.
        self._update_hover_tooltip(screen, ev.world_pos)
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        screen = (event.position().x(), event.position().y())
        mods = qt_modifiers_to_logical(event.modifiers())
        if (
            self._drag_action is not None
            or self._primary_item is not None
            or self._dragging_items
            or self._rubber_band_overlay is not None
        ):
            self._end_pointer_interactions(
                screen,
                mods,
                commit_rubber_band=True,
            )
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        mods, direction = wheel_event_pair(event)
        screen = (event.position().x(), event.position().y())
        # Offer the wheel event to the topmost item under the cursor first.
        # Any item whose handle_input returns True consumes the event and
        # prevents the canvas-level zoom gesture from firing.  This lets
        # items with their own scroll behaviour (e.g. a scrollable text area
        # or an embedded scrollbar) override the canvas default.
        ad = event.angleDelta()
        _wheel_ev = self._make_event(
            CANVAS_ITEM_WHEEL,
            "wheel",
            screen,
            mods,
            delta=(float(ad.x()), float(ad.y())),
        )
        if self._route_to_topmost(_wheel_ev.world_pos, _wheel_ev) is not None:
            event.accept()
            return
        bindings = get_default_bindings()
        if bindings.matches_wheel(CANVAS_ZOOM_IN.id, mods, direction):
            if self.camera.is_locked:
                event.accept()
                return
            self._zoom_about(screen, self._ZOOM_STEP)
            event.accept()
            return
        if bindings.matches_wheel(CANVAS_ZOOM_OUT.id, mods, direction):
            if self.camera.is_locked:
                event.accept()
                return
            self._zoom_about(screen, 1.0 / self._ZOOM_STEP)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._key_input_item is not None:
            screen = self._cursor_screen if self._cursor_screen is not None else (
                0.0, 0.0)
            mods = qt_modifiers_to_logical(event.modifiers())
            ev = CanvasInputEvent(
                action=CANVAS_ITEM_KEY,
                phase="press",
                world_pos=self._screen_to_world(*screen),
                screen_pos=screen,
                modifiers=mods,
                key=int(event.key()),
                text=event.text(),
            )
            if self._key_input_item.handle_input(ev):
                event.accept()
                return

        seq = QKeySequence(event.keyCombination()).toString()
        bindings = get_default_bindings()
        if bindings.matches_key(CANVAS_UNDO.id, seq):
            if self.capabilities.allow_undo_redo and self.history is not None:
                self.history.undo()
            event.accept()
            return
        if bindings.matches_key(CANVAS_REDO.id, seq):
            if self.capabilities.allow_undo_redo and self.history is not None:
                self.history.redo()
            event.accept()
            return
        if bindings.matches_key(CANVAS_DESELECT_ALL.id, seq):
            if self.capabilities.allow_selection:
                self.clear_selection()
            event.accept()
            return
        if bindings.matches_key(CANVAS_SELECT_ALL.id, seq):
            if self.capabilities.allow_selection:
                self.clear_selection()
                for item in self.items():
                    self.select_item(item, additive=True)
            event.accept()
            return
        if bindings.matches_key(CANVAS_DELETE_SELECTED.id, seq):
            if self.capabilities.allow_selection and self.capabilities.allow_add_remove:
                for item in list(self.selected_items()):
                    self.remove_item_command(item)
            event.accept()
            return
        if bindings.matches_key(CANVAS_COPY.id, seq):
            if self.capabilities.allow_clipboard and self.capabilities.allow_selection:
                self._clipboard = list(self.selected_items())
            event.accept()
            return
        if bindings.matches_key(CANVAS_CUT.id, seq):
            if self.capabilities.allow_clipboard and self.capabilities.allow_selection and self.capabilities.allow_add_remove:
                self._clipboard = list(self.selected_items())
                for item in self._clipboard:
                    self.remove_item_command(item)
                self.clear_selection()
            event.accept()
            return
        if bindings.matches_key(CANVAS_PASTE.id, seq):
            if self.capabilities.allow_clipboard and self.capabilities.allow_add_remove and self._clipboard:
                if self.item_clone_fn is not None:
                    self.clear_selection()
                    for src in self._clipboard:
                        clone = self.item_clone_fn(src)
                        if clone is None:
                            continue
                        self.add_item_command(clone)
                        self.select_item(clone, additive=True)
            event.accept()
            return
        if bindings.matches_key(CANVAS_RESET_VIEW.id, seq):
            if self.camera.is_locked:
                event.accept()
                return
            self.reset_view(animate=True)
            event.accept()
            return
        if bindings.matches_key(CANVAS_FIT_CONTENT.id, seq):
            if self.camera.is_locked:
                event.accept()
                return
            self.fit_to_content(animate=True)
            event.accept()
            return
        if bindings.matches_key(CANVAS_RESET_ZOOM.id, seq):
            if self.camera.is_locked:
                event.accept()
                return
            self.reset_zoom(animate=True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if self._key_input_item is not None:
            screen = self._cursor_screen if self._cursor_screen is not None else (
                0.0, 0.0)
            mods = qt_modifiers_to_logical(event.modifiers())
            ev = CanvasInputEvent(
                action=CANVAS_ITEM_KEY,
                phase="release",
                world_pos=self._screen_to_world(*screen),
                screen_pos=screen,
                modifiers=mods,
                key=int(event.key()),
                text=event.text(),
            )
            if self._key_input_item.handle_input(ev):
                event.accept()
                return
        super().keyReleaseEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._cursor_screen = None
        self._clear_hover_tooltip()
        self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------------ #
    # Drag helpers                                                         #
    # ------------------------------------------------------------------ #

    def _begin_drag(
        self, action_id: str, screen_anchor: tuple[float, float]
    ) -> None:
        # If a view animation is still settling, snap to its target so
        # the drag anchor is stable (no compounding lerp drift). Both
        # the time-based go_to and the exponential pump are handled
        # by reading their respective targets first, then cancelling.
        snap_target: ViewTransform | None = (
            self.camera._goto_target_view  # noqa: SLF001
            if self.camera._goto_target_view is not None  # noqa: SLF001
            else self.camera._anim_target_view  # noqa: SLF001
        )
        if snap_target is not None:
            self.camera.set_view(snap_target)
        self.camera.cancel_view_animation()
        self._drag_action = action_id
        self._drag_screen_anchor = screen_anchor
        self._drag_view_anchor = self.camera.view()
        self._drag_world_anchor = self._drag_view_anchor.screen_to_world(
            screen_anchor, (float(self.width()), float(self.height()))
        )
        self._drag_rotate_reference_angle = None
        if action_id == CANVAS_ROTATE.id:
            self._set_texture_overlay_pivot(
                screen_anchor,
                lock=True,
                pin_view_changes=True,
                reference_view=self._drag_view_anchor,
            )
        elif action_id == CANVAS_PAN.id:
            self._set_texture_overlay_pivot(
                screen_anchor,
                lock=False,
                pin_view_changes=False,
                reference_view=self._drag_view_anchor,
            )

    def _handle_drag_motion(self, screen: tuple[float, float]) -> None:
        if (
            self._drag_screen_anchor is None
            or self._drag_view_anchor is None
            or self._drag_world_anchor is None
        ):
            return
        ax, ay = self._drag_screen_anchor
        sx, sy = screen
        dx_screen = sx - ax

        if self._drag_action == CANVAS_PAN.id:
            # Compute world-space drag from the anchor view directly.
            # This preserves expected screen-direction panning even when
            # the canvas is rotated.
            viewport = (float(self.width()), float(self.height()))
            world_anchor = self._drag_view_anchor.screen_to_world(
                self._drag_screen_anchor, viewport
            )
            world_current = self._drag_view_anchor.screen_to_world(
                screen, viewport
            )
            wdx = world_current[0] - world_anchor[0]
            wdy = world_current[1] - world_anchor[1]
            cx, cy = self._drag_view_anchor.center_world
            # Push the *target* (mouse-pinned) view; visible view lerps
            # toward it each animation tick for snappy smoothing.
            target = self._drag_view_anchor.with_center(
                (cx - wdx, cy - wdy)
            )
            self.camera.begin_view_animation(target, alpha=self._pan_alpha)
        elif self._drag_action == CANVAS_ROTATE.id:
            import math
            vx = sx - ax
            vy = sy - ay
            if abs(vx) < 1e-6 and abs(vy) < 1e-6:
                return
            angle = math.atan2(vy, vx)
            if self._drag_rotate_reference_angle is None:
                # First non-zero ray establishes the reference direction.
                self._drag_rotate_reference_angle = angle
                return
            delta = angle - self._drag_rotate_reference_angle
            while delta > math.pi:
                delta -= 2.0 * math.pi
            while delta < -math.pi:
                delta += 2.0 * math.pi
            new_rot = (
                self._drag_view_anchor.rotation_radians + delta
            )
            rotated = self._drag_view_anchor.with_rotation(new_rot)

            # Keep the initial press world point pinned under the same
            # screen anchor while rotating.
            viewport = (float(self.width()), float(self.height()))
            world_after = rotated.screen_to_world(
                self._drag_screen_anchor, viewport)
            cx, cy = rotated.center_world
            target = rotated.with_center(
                (
                    cx - (world_after[0] - self._drag_world_anchor[0]),
                    cy - (world_after[1] - self._drag_world_anchor[1]),
                )
            )
            self.camera.set_view(target)

    def _end_drag(self, screen: tuple[float, float]) -> None:
        if self._drag_action == CANVAS_ROTATE.id:
            # Snap to nearest 90° if within threshold.
            import math
            current_view = self.camera.view()
            rot = current_view.rotation_radians % (2 * math.pi)
            quarter = math.pi / 2
            nearest = round(rot / quarter) * quarter
            if abs(rot - nearest) < math.radians(self._ROTATION_SNAP_DEG):
                self.camera.set_view(
                    current_view.with_rotation(nearest % (2 * math.pi))
                )
        self._drag_action = None
        self._drag_screen_anchor = None
        self._drag_view_anchor = None
        self._drag_world_anchor = None
        self._drag_rotate_reference_angle = None
        self._clear_texture_overlay_pivot_lock()

    def _zoom_about(
        self, screen: tuple[float, float], factor: float
    ) -> None:
        # Keep the world point under ``screen`` fixed in screen space.
        # Wheel zoom is animated for visual smoothness; rapid wheel
        # ticks accumulate into the target view (no snapping).
        # Use the current animation target (if any) only for zoom-magnitude
        # compounding. Pinning must be computed from the currently displayed
        # view; anchoring against a future target causes cursor drift/pops
        # under rapid successive wheel ticks.
        current = self.camera.view()
        target_basis = (
            self.camera._anim_target_view  # noqa: SLF001
            if self.camera._anim_target_view is not None  # noqa: SLF001
            else current
        )
        self._set_texture_overlay_pivot(
            screen, lock=True, reference_view=current)
        world_under = current.screen_to_world(
            screen, (float(self.width()), float(self.height()))
        )
        new_zoom = max(
            self._MIN_ZOOM,
            min(self._MAX_ZOOM, target_basis.zoom * factor),
        )
        if new_zoom == target_basis.zoom:
            return
        new_view = target_basis.with_zoom(new_zoom)
        world_after = new_view.screen_to_world(
            screen, (float(self.width()), float(self.height()))
        )
        cx, cy = new_view.center_world
        # Shift the centre so the world point under ``screen`` matches
        # the original ``world_under``. ``world_after`` is where the
        # cursor lands without any centre shift; subtract the delta to
        # cancel it out.
        dx = world_after[0] - world_under[0]
        dy = world_after[1] - world_under[1]
        target = new_view.with_center((cx - dx, cy - dy))
        self.camera.begin_view_animation(target, alpha=self._zoom_alpha)

    def _set_texture_overlay_pivot(
        self,
        screen: tuple[float, float],
        *,
        lock: bool,
        pin_view_changes: bool = True,
        reference_view: ViewTransform | None = None,
    ) -> None:
        view = reference_view if reference_view is not None else self.camera.view()
        viewport_logical_px = (float(self.width()), float(self.height()))
        dpr = float(max(self.devicePixelRatioF(), 1.0))
        for overlay in self.scene.overlays():
            setter = getattr(overlay, "set_interaction_pivot_screen", None)
            if callable(setter):
                setter(
                    screen,
                    lock=lock,
                    pin_view_changes=pin_view_changes,
                    view=view,
                    viewport_logical_px=viewport_logical_px,
                    device_pixel_ratio=dpr,
                )

    def _clear_texture_overlay_pivot_lock(self) -> None:
        for overlay in self.scene.overlays():
            clearer = getattr(overlay, "clear_interaction_pivot_lock", None)
            if callable(clearer):
                clearer()

    # ------------------------------------------------------------------ #
    # Add / remove command wrappers (D2)                                  #
    # ------------------------------------------------------------------ #

    def add_item_command(self, item: CanvasItem) -> None:
        """Add *item* via a history command (undoable if `allow_undo_redo`)."""
        if self.history is not None:
            self.history.push(AddItemCommand(self.scene, item))
        else:
            self.scene.add_item(item)

    def remove_item_command(self, item: CanvasItem) -> None:
        """Remove *item* via a history command (undoable if `allow_undo_redo`)."""
        if self.history is not None:
            self.history.push(RemoveItemCommand(self.scene, item))
        else:
            self.scene.remove_item(item)

    # ------------------------------------------------------------------ #
    # Rubber-band drag helpers (C3)                                       #
    # ------------------------------------------------------------------ #

    def _begin_rubber_band(
        self, screen: tuple[float, float], *, subtractive: bool = False
    ) -> None:
        """Start a rubber-band selection drag at *screen*.

        Args:
            subtractive: When ``True``, items inside the final rect will be
                         *deselected* rather than added to the selection.
        """
        # If an old overlay was left behind (e.g. missed mouse-release),
        # remove it before starting a fresh marquee drag.
        self._cancel_rubber_band()

        overlay = RubberBandOverlay()
        overlay.set_start(*screen)
        self.add_overlay(overlay)
        self._rubber_band_overlay = overlay
        self._rubber_band_screen_start = screen
        self._rubber_band_subtractive = subtractive
        if not self._rubber_band_mouse_grabbed:
            self.grabMouse()
            self._rubber_band_mouse_grabbed = True

    def _matches_rubber_band_selection(self, item: CanvasItem, world_aabb: AABB) -> bool:
        """Return whether *item* should be selected by rubber-band in *world_aabb*.

        Items can implement an optional ``selection_intersects_aabb(world_aabb)``
        method for geometry-accurate overlap checks. If missing, the default
        scene AABB broad-phase match is accepted.
        """
        predicate = getattr(item, "selection_intersects_aabb", None)
        if not callable(predicate):
            return True
        try:
            return bool(predicate(world_aabb))
        except Exception:
            return True

    def _end_rubber_band(self) -> None:
        """Commit rubber-band selection and remove the overlay."""
        if self._rubber_band_overlay is None:
            return
        x0, y0, x1, y1 = self._rubber_band_overlay.screen_rect()
        view = self.view()
        viewport = (float(self.width()), float(self.height()))
        # Convert screen rect corners to world space.
        wx0, wy0 = view.screen_to_world((x0, y0), viewport)
        wx1, wy1 = view.screen_to_world((x1, y1), viewport)
        world_aabb = AABB(
            min(wx0, wx1), min(wy0, wy1),
            max(wx0, wx1), max(wy0, wy1),
        )
        if world_aabb.width > 0 and world_aabb.height > 0:
            hits = [
                item
                for item in self.scene.items_in_aabb(world_aabb)
                if item.selectable and self._matches_rubber_band_selection(item, world_aabb)
            ]
            if hits:
                if getattr(self, "_rubber_band_subtractive", False):
                    self.scene.deselect_items(hits)
                else:
                    selected_before = self.selected_items()
                    preferred_active = self.active_selected_item()
                    if not selected_before:
                        preferred_active = hits[0]
                    self.scene.select_items(
                        hits,
                        additive=True,
                        preferred_active=preferred_active,
                    )
        self._cancel_rubber_band()
        self.update()

    def _cancel_rubber_band(self) -> None:
        """Remove any active rubber-band overlay without committing selection."""
        if self._rubber_band_overlay is not None:
            self.remove_overlay(self._rubber_band_overlay)
            self._rubber_band_overlay = None
        self._rubber_band_screen_start = None
        self._rubber_band_subtractive = False
        if self._rubber_band_mouse_grabbed:
            self.releaseMouse()
            self._rubber_band_mouse_grabbed = False

    def focusOutEvent(self, event: QFocusEvent) -> None:
        # If focus is lost mid-gesture, end pointer interactions so no
        # drag/marquee state can remain latched.
        if not hasattr(self, "_drag_action"):
            super().focusOutEvent(event)
            return
        cursor_screen = getattr(self, "_cursor_screen", None)
        self._end_pointer_interactions(
            cursor_screen,
            frozenset(),
            commit_rubber_band=False,
        )
        super().focusOutEvent(event)

    def event(self, event: QEvent) -> bool:
        # Qt sends UngrabMouse when capture is forcibly lost (e.g. release
        # happened outside our control). Tear down pointer state to avoid
        # sticky drag-box / drag interactions.
        if event.type() == QEvent.Type.UngrabMouse:
            # Guard against spurious ungrab notifications while the user is
            # still actively holding a button (reported on some platforms).
            # In that case, keep the in-flight marquee/drag alive.
            if QGuiApplication.mouseButtons() != Qt.MouseButton.NoButton:
                return super().event(event)
            if not hasattr(self, "_drag_action"):
                return super().event(event)
            cursor_screen = getattr(self, "_cursor_screen", None)
            self._end_pointer_interactions(
                cursor_screen,
                frozenset(),
                commit_rubber_band=False,
            )
        return super().event(event)

    # ------------------------------------------------------------------ #
    # Widget-managed item drag helpers (B2)                               #
    # ------------------------------------------------------------------ #

    def _end_pointer_interactions(
        self,
        screen: tuple[float, float] | None,
        mods: frozenset[Modifier],
        *,
        commit_rubber_band: bool,
    ) -> None:
        """End all pointer-driven transient states.

        This is used as a failsafe when Qt mouse capture/focus is lost so
        drag state never remains latched.
        """
        release_screen = screen if screen is not None else (0.0, 0.0)
        if self._drag_action is not None:
            self._end_drag(release_screen)
        if self._primary_item is not None:
            primary_item = self._primary_item
            self._primary_item = None
            ev = self._make_event(
                CANVAS_PRIMARY, "release", release_screen, mods)
            primary_item.handle_input(ev)
        if self._dragging_items:
            self._end_item_drag()
        if self._rubber_band_overlay is not None:
            if commit_rubber_band:
                self._end_rubber_band()
            else:
                self._cancel_rubber_band()

    def _begin_item_drag(
        self, items: list[CanvasItem], screen: tuple[float, float]
    ) -> None:
        """Start a widget-managed drag for *items*."""
        self._dragging_items = list(items)
        self._item_drag_screen_prev = screen
        self._item_drag_world_deltas = {id(it): (0.0, 0.0) for it in items}
        view = self.view()
        viewport = (float(self.width()), float(self.height()))
        wp = view.screen_to_world(screen, viewport)
        for item in self._dragging_items:
            item.on_drag_begin(wp)

    def _handle_item_drag_motion(self, screen: tuple[float, float]) -> None:
        """Update dragged items as the mouse moves to *screen*."""
        if not self._dragging_items or self._item_drag_screen_prev is None:
            return
        view = self.view()
        viewport = (float(self.width()), float(self.height()))
        prev_w = view.screen_to_world(self._item_drag_screen_prev, viewport)
        curr_w = view.screen_to_world(screen, viewport)
        dx = curr_w[0] - prev_w[0]
        dy = curr_w[1] - prev_w[1]
        for item in self._dragging_items:
            item.on_drag((dx, dy))
            old_dx, old_dy = self._item_drag_world_deltas[id(item)]
            self._item_drag_world_deltas[id(item)] = (old_dx + dx, old_dy + dy)
        self._item_drag_screen_prev = screen
        self.update()

    def _end_item_drag(self) -> None:
        """Finalise the item drag, push a command, and emit `items_moved`."""
        if not self._dragging_items:
            return
        for item in self._dragging_items:
            item.on_drag_end()
        deltas = [
            (item, *self._item_drag_world_deltas[id(item)])
            for item in self._dragging_items
        ]
        moved = list(self._dragging_items)
        self._dragging_items = []
        self._item_drag_screen_prev = None
        self._item_drag_world_deltas = {}
        if any(abs(dx) > 1e-9 or abs(dy) > 1e-9 for _, dx, dy in deltas):
            cmd = MoveItemsCommand(deltas)
            # Register the command in history WITHOUT re-executing it
            # (the drag already applied the deltas live).
            if self.history is not None:
                self.history.push_already_executed(cmd)
            self.items_moved.emit(moved)
        self.update()

    # ------------------------------------------------------------------ #
    # Tablet                                                               #
    # ------------------------------------------------------------------ #

    def tabletEvent(self, event: QTabletEvent) -> None:
        # Handle tablet events directly — do NOT rely on Qt synthesising
        # QMouseEvents from unhandled tablet events because synthesis is
        # unreliable when the pen tip is not in contact with the surface
        # (hover state).  We replicate the same logic as the mouse
        # handlers so that barrel-button pan (MMB) works without tip
        # contact.
        screen = (event.position().x(), event.position().y())
        mods = qt_modifiers_to_logical(event.modifiers())
        etype = event.type()
        wp = self._screen_to_world(*screen)
        bindings = get_default_bindings()

        if etype == QEvent.Type.TabletPress:
            # --- View gestures (barrel button / side button) ---
            # event.button() is the button that triggered this press.
            button = qt_button_to_logical(event.button())
            if button is not None:
                if bindings.matches_mouse(
                    CANVAS_PAN.id, button, mods, GestureKind.DRAG
                ):
                    if not self.camera.is_locked:
                        self._begin_drag(CANVAS_PAN.id, screen)
                    event.accept()
                    return
                if bindings.matches_mouse(
                    CANVAS_ROTATE.id, button, mods, GestureKind.DRAG
                ):
                    if not self.camera.is_locked:
                        self._begin_drag(CANVAS_ROTATE.id, screen)
                    event.accept()
                    return

            # --- Primary (pen tip) press ---
            ev = self._make_event(
                CANVAS_PRIMARY, "press", screen, mods,
                pressure=float(event.pressure()), is_tablet=True,
            )
            consumer = self._route_to_topmost(wp, ev)
            if consumer is not None:
                self._primary_item = consumer
                self._key_input_item = consumer
                event.accept()
                return

        elif etype == QEvent.Type.TabletMove:
            self._cursor_screen = screen
            self.cursor_world_pos.emit(wp[0], wp[1])

            # Active view drag (pan / rotate started by barrel button).
            if self._drag_action is not None:
                self._handle_drag_motion(screen)
                event.accept()
                return

            # Active primary item drag (pen tip painting).
            if self._primary_item is not None:
                ev = self._make_event(
                    CANVAS_PRIMARY, "drag", screen, mods,
                    pressure=float(event.pressure()), is_tablet=True,
                )
                self._primary_item.handle_input(ev)
                event.accept()
                return

            self.update()

        elif etype == QEvent.Type.TabletRelease:
            # --- View drag release ---
            # End any active view drag on any tablet button release.  We
            # don't re-check the binding because modifiers may have
            # changed during the drag and we never want to leave the drag
            # state stranded.
            if self._drag_action is not None:
                self._end_drag(screen)
                event.accept()
                return

            # --- Primary (pen tip) release ---
            if self._primary_item is not None:
                ev = self._make_event(
                    CANVAS_PRIMARY, "release", screen, mods,
                    pressure=float(event.pressure()), is_tablet=True,
                )
                self._primary_item.handle_input(ev)
                self._primary_item = None
                event.accept()
                return

        super().tabletEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(800, 600)

    # ------------------------------------------------------------------ #
    # Drag-and-drop: image files from outside the application             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _image_urls_from_event(event: QDragEnterEvent) -> list[str]:
        """Return file paths for image URLs in *event*'s MIME data."""
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        paths: list[str] = []
        for url in mime.urls():
            local = url.toLocalFile()
            if local:
                suffix = "." + \
                    local.rsplit(".", 1)[-1].lower() if "." in local else ""
                if suffix in IMAGE_EXTENSIONS:
                    paths.append(local)
        return paths

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._image_urls_from_event(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._image_urls_from_event(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._image_urls_from_event(event)
        if not paths:
            event.ignore()
            return

        vp = (float(self.width()), float(self.height()))
        view = self.camera.view()
        drop_screen = (float(event.position().x()),
                       float(event.position().y()))
        world_pt = view.screen_to_world(drop_screen, vp)

        for path in paths:
            from pathlib import Path as _Path
            from PySide6.QtGui import QImageReader
            reader = QImageReader(path)
            natural_w = float(reader.size().width()
                              ) if reader.size().isValid() else 256.0
            natural_h = float(reader.size().height()
                              ) if reader.size().isValid() else 256.0
            half_w = natural_w / 2.0
            half_h = natural_h / 2.0
            world_rect = QRectF(
                world_pt[0] - half_w, world_pt[1] - half_h,
                natural_w, natural_h,
            )
            item = ImageCanvasItem(
                image_path=_Path(path), world_rect=world_rect)
            self.add_item(item)

        event.acceptProposedAction()


__all__ = ["Canvas2D", "Canvas2DWidget"]

# Backward-compat alias — all existing code that uses ``Canvas2D`` keeps
# working without any changes.
Canvas2D = Canvas2DWidget
