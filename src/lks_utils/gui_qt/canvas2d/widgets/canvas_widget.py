"""`Canvas2DWidget`: a reusable Qt widget hosting a 2-D scene of `CanvasObject`s.

``Canvas2D`` is the public alias kept for backward compatibility.

This is the **foundation widget** for the painter, node graphs, and
any future tool that needs an unbounded 2-D viewport with pan/zoom/
rotation. It knows nothing about tiles, brushes, or pixels.

Internally the widget delegates to three extracted components:

* :class:`~lks_utils.gui_qt.canvas2d.core.scene2d.Scene2D` — object/overlay
  data model, dirty tracking, spatial queries.
* :class:`~lks_utils.gui_qt.canvas2d.core.camera2d.Camera2D` — view state
  and animated navigation.
* :class:`~lks_utils.gui_qt.canvas2d.render.canvas_renderer.Canvas2DRenderer`
  — stateless paint orchestration.

All three are public attributes (``canvas.scene``, ``canvas.camera``,
``canvas.renderer``) so advanced callers can share a scene between
multiple widgets or drive the camera from outside the widget.

Design notes / deviations from the spec:

* The foundation uses a plain ``QWidget`` with ``QPainter`` rather than
  ``QOpenGLWidget`` + ModernGL. ``QPainter`` gives items a simple,
  hardware-accelerated drawing surface and lets the foundation be
  testable without a GPU. A future GPU-backed subclass can swap in
  ``QOpenGLWidget`` for objects that need raw GL textures (e.g. the
  TileTree renderer).
* World-space drawing is provided by setting the painter's transform
  to the view's world->screen affine before each object paints. Objects
  draw in world coordinates; the transform handles pan/zoom/rotation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import (
    QEvent,
    QPointF,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
)
from PySide6.QtWidgets import QWidget

from lks_utils.gui_qt.canvas2d.interaction.canvas_commands.command_add_object import AddObjectCommand
from lks_utils.gui_qt.canvas2d.interaction.canvas_commands.command_remove_object import RemoveObjectCommand
from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_selection import SelectionOverlay
from lks_utils.gui_qt.canvas2d.widgets.canvas_widget_policies import CanvasWidgetPolicies
from lks_utils.gui_qt.canvas2d.widgets._drag_controller import DragControllerMixin
from lks_utils.gui_qt.canvas2d.widgets._hover_tooltip import HoverTooltipMixin
from lks_utils.gui_qt.canvas2d.widgets._input_routing import InputRoutingMixin
from lks_utils.gui_qt.canvas2d.interaction.command_history import CommandHistory
from lks_utils.gui_qt.canvas2d.core.camera2d import Camera2D
from lks_utils.gui_qt.canvas2d.render.canvas_renderer import Canvas2DRenderer
from lks_utils.gui_qt.canvas2d.core.canvas_document import (
    CanvasDocument,
    _view_from_dict,
    _view_to_dict,
)
from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.gui_qt.canvas2d.canvas_object_registry import get_canvas_object_type
from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_image import IMAGE_EXTENSIONS, ImageCanvasObject
from lks_utils.gui_qt.canvas2d.core.scene2d import Scene2D
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay
from lks_utils.gui_qt.qt_paint_profile_mixin import QtPaintProfileMixin

if TYPE_CHECKING:
    from pathlib import Path


class CanvasWidgetBase(QWidget):
    """Base for canvas2d viewport Qt shells backed by scene/camera/renderer."""

    scene: Scene2D
    camera: Camera2D
    renderer: Canvas2DRenderer


class Canvas2DWidget(
    QtPaintProfileMixin,
    HoverTooltipMixin,
    DragControllerMixin,
    InputRoutingMixin,
    CanvasWidgetBase,
):
    """A 2-D viewport widget hosting `CanvasObject`s and overlays.

    Pan / zoom / rotate, object placement, dirty tracking, and built-in
    overlays. Add objects via :meth:`add_object`, overlays via
    :meth:`add_overlay`. The current `ViewTransform` is available via
    :meth:`view`; replace it via :meth:`set_view`.

    The widget owns three public sub-components:

    * **scene** (:class:`~lks_utils.gui_qt.canvas2d.core.scene2d.Scene2D`):
      objects, overlays, dirty tracker.
    * **camera** (:class:`~lks_utils.gui_qt.canvas2d.core.camera2d.Camera2D`):
      view state, animated navigation, bookmarks.
    * **renderer** (:class:`~lks_utils.gui_qt.canvas2d.render.canvas_renderer.Canvas2DRenderer`):
      stateless paint orchestration.

    Signals:
        view_changed(ViewTransform): View transform changed.
        object_added(CanvasObject)
        object_removed(CanvasObject)
        object_changed(CanvasObject, object): An object requested a repaint
            (e.g. moved, resized, restyled). Second arg is the dirty
            world AABB (or ``None`` for "whole object"). Useful for
            companion widgets like the minimap that need to refresh
            on object edits, not just on add/remove.
        cursor_world_pos(float, float): Last hovered world position.
            Useful for HUDs.
    """

    view_changed = Signal(object)       # ViewTransform
    object_added = Signal(object)           # CanvasObject
    object_removed = Signal(object)         # CanvasObject
    object_changed = Signal(object, object)  # CanvasObject, AABB | None
    cursor_world_pos = Signal(float, float)
    #: Re-exported from :attr:`scene`'s owned ``SelectionModel``.
    selection_changed = Signal()
    #: Fires when active selected object changes.
    active_selection_changed = Signal(object)
    #: Fires with the new ``is_modified`` value when dirty state changes.
    modified_changed = Signal(bool)
    #: Emitted after a widget-managed object drag is committed to history.
    objects_moved = Signal(list)


    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        capabilities: CanvasWidgetPolicies | None = None,
        scene: Scene2D | None = None,
        camera: Camera2D | None = None,
    ) -> None:
        super().__init__(parent)

        self.capabilities: CanvasWidgetPolicies = (
            capabilities if capabilities is not None else CanvasWidgetPolicies()
        )

        # Public sub-components — may be shared across multiple widgets.
        self.scene: Scene2D = scene if scene is not None else Scene2D(self)
        self.camera: Camera2D = camera if camera is not None else Camera2D(
            self)
        self.renderer: Canvas2DRenderer = Canvas2DRenderer()



        # Clipboard state.
        # object_clone_fn must be set by the owner to enable paste.
        # Signature: (obj: CanvasObject) -> CanvasObject | None
        from typing import Callable
        self.object_clone_fn: Callable[[CanvasObject],
                                     CanvasObject | None] | None = None
        self._clipboard: list[CanvasObject] = []
        self._paste_offset: tuple[float, float] = (20.0, 20.0)

        self._init_input_routing()
        self._init_drag_controller()
        self._init_hover_tooltip()

        self.history: CommandHistory | None = (
            self.create_command_history()
            if self.capabilities.allow_undo_redo
            else None
        )

        # Wire camera → widget.
        self.camera.view_changed.connect(self._on_camera_view_changed)
        self._is_modified: bool = False

        # Wire scene → widget.
        self.scene.object_added.connect(self._on_scene_object_added)
        self.scene.object_removed.connect(self._on_scene_object_removed)
        self.scene.object_changed.connect(self._on_scene_object_changed)
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
        for it in self.scene.objects():
            it.on_view_changed(view)
        for ov in self.scene.overlays():
            ov.on_view_changed(view)
        self.view_changed.emit(view)
        self.update()

    def _on_scene_object_added(self, obj: CanvasObject) -> None:
        from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability_host import (
            CapabilityHostObject,
        )

        if isinstance(obj, CapabilityHostObject):
            obj.bind_host_services(
                scene=self.scene,
                command_history=self.history,
                view_zoom=lambda: self.camera.view().zoom,
                view_transform=lambda: self.camera.view(),
                viewport_size_px=lambda: (float(self.width()), float(self.height())),
            )
        self.object_added.emit(obj)
        self._set_modified(True)

    def _on_scene_object_removed(self, obj: CanvasObject) -> None:
        if self._primary_object is obj:
            self._primary_object = None
        if self._key_input_object is obj:
            self._key_input_object = None
        self.object_removed.emit(obj)
        self._set_modified(True)

    def _on_scene_object_changed(self, obj: CanvasObject, region: object) -> None:
        self.object_changed.emit(obj, region)
        # Only mark modified when the object opts into persistence.
        if obj.to_dict() is not None:
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
    # Object / overlay management (delegates to Scene2D)                    #
    # ------------------------------------------------------------------ #

    def add_object(self, obj: CanvasObject, z_order: int | None = None) -> None:
        self.scene.add_object(obj, z_order)

    def remove_object(self, obj: CanvasObject) -> None:
        self.scene.remove_object(obj)

    def objects(self) -> list[CanvasObject]:
        return self.scene.objects()

    def add_overlay(self, overlay: ViewportOverlay) -> None:
        self.scene.add_overlay(overlay)

    def remove_overlay(self, overlay: ViewportOverlay) -> None:
        self.scene.remove_overlay(overlay)

    def overlays(self) -> list[ViewportOverlay]:
        return self.scene.overlays()

    def enable_debug_bounds(self, *, show_labels: bool = True) -> None:
        """Attach a :class:`~lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_canvas_bounds.CanvasBoundsOverlay`.

        Draws 1px red AABBs around every scene object in screen space.
        Idempotent — calling more than once adds only one overlay.
        """
        from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_canvas_bounds import CanvasBoundsOverlay

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

    def select_object(self, obj: CanvasObject, *, additive: bool = False) -> None:
        """Select *obj* (see :meth:`~Scene2D.select_object`)."""
        self.scene.select_object(obj, additive=additive)
        if self.capabilities.bring_selected_to_front:
            self.scene.bring_object_to_front(obj)

    def toggle_object_selection(self, obj: CanvasObject) -> None:
        """Toggle *obj* in the current selection set."""
        self.scene.toggle_object_selection(obj)
        active = self.scene.active_selected_object()
        if self.capabilities.bring_selected_to_front and active is not None:
            self.scene.bring_object_to_front(active)

    def select_range_to_object(self, obj: CanvasObject, *, additive: bool = False) -> None:
        """Select anchor-to-object range using scene order."""
        self.scene.select_range_to(obj, additive=additive)
        active = self.scene.active_selected_object()
        if self.capabilities.bring_selected_to_front and active is not None:
            self.scene.bring_object_to_front(active)

    def deselect_object(self, obj: CanvasObject) -> None:
        """Remove *obj* from the selection."""
        self.scene.deselect_object(obj)

    def clear_selection(self) -> None:
        """Clear the selection."""
        self.scene.clear_selection()

    def selected_objects(self) -> list[CanvasObject]:
        """Return a snapshot of the current selection."""
        return self.scene.selected_objects()

    def active_selected_object(self) -> CanvasObject | None:
        """Return the active selected object, if any."""
        return self.scene.active_selected_object()

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

        objects_data: list[dict] = []
        for obj in self.scene.objects():
            d = obj.to_dict()
            if d is not None:
                objects_data.append(d)

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
            objects=objects_data,
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
        # Clear existing objects (selection is cleaned up automatically by
        # Scene2D.remove_object).
        for obj in list(self.scene.objects()):
            self.scene.remove_object(obj)
        for ov in list(self.scene.overlays()):
            self.scene.remove_overlay(ov)

        # Reconstruct objects.
        for object_dict in doc.objects:
            type_name = object_dict.get("type", "")
            cls = get_canvas_object_type(type_name)
            if cls is None:
                continue  # unknown type — skip silently
            try:
                obj = cls.from_dict(object_dict)
            except Exception:  # noqa: BLE001
                continue
            self.scene.add_object(obj)

        # Reconstruct overlays.
        for ov_dict in doc.overlays:
            type_name = ov_dict.get("type", "")
            cls = get_canvas_object_type(type_name)
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



    # ------------------------------------------------------------------ #
    # Drag helpers                                                         #
    # ------------------------------------------------------------------ #


    # ------------------------------------------------------------------ #
    # Add / remove command wrappers (D2)                                  #
    # ------------------------------------------------------------------ #

    def add_object_command(self, obj: CanvasObject) -> None:
        """Add *obj* via a history command (undoable if `allow_undo_redo`)."""
        if self.history is not None:
            self.history.push(AddObjectCommand(self.scene, obj))
        else:
            self.scene.add_object(obj)

    def remove_object_command(self, obj: CanvasObject) -> None:
        """Remove *obj* via a history command (undoable if `allow_undo_redo`)."""
        if self.history is not None:
            self.history.push(RemoveObjectCommand(self.scene, obj))
        else:
            self.scene.remove_object(obj)

    # ------------------------------------------------------------------ #
    # Rubber-band drag helpers (C3)                                       #
    # ------------------------------------------------------------------ #



    # ------------------------------------------------------------------ #
    # Widget-managed object drag helpers (B2)                               #
    # ------------------------------------------------------------------ #


    # ------------------------------------------------------------------ #
    # Tablet                                                               #
    # ------------------------------------------------------------------ #


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
            obj = ImageCanvasObject(
                image_path=_Path(path), world_rect=world_rect)
            self.add_object(obj)

        event.acceptProposedAction()


__all__ = ["Canvas2D", "Canvas2DWidget", "CanvasWidgetBase"]

# Backward-compat alias — all existing code that uses ``Canvas2D`` keeps
# working without any changes.
Canvas2D = Canvas2DWidget
