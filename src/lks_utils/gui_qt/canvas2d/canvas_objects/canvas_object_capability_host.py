"""CapabilityHostObject — composes optional behaviors via attached capabilities."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF

from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform
from lks_utils.spatial.aabb import AABB

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability import CanvasObjectCapability
    from lks_utils.gui_qt.canvas2d.core.scene2d import Scene2D
    from lks_utils.gui_qt.canvas2d.core.selection_model import SelectionModel
    from lks_utils.gui_qt.canvas2d.interaction.canvas_command import CanvasCommand
    from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CanvasInputEvent
    from lks_utils.gui_qt.canvas2d.interaction.command_history import CommandHistory
    from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext


class CapabilityHostObject(CanvasObject):
    """Canvas object that delegates paint/input to content + attached capabilities."""

    manages_own_selection_highlight = True

    def __init__(
        self,
        *,
        host_rect: QRectF,
        content: CanvasObject | None = None,
    ) -> None:
        super().__init__()
        self._host_rect = QRectF(host_rect)
        self._content = content
        self._capabilities: list[CanvasObjectCapability] = []
        self._unknown_capability_blocks: dict[str, dict] = {}
        self._scene: Scene2D | None = None
        self._command_history: CommandHistory | None = None
        self._view_zoom: Callable[[], float] = lambda: 1.0
        self._view_transform: Callable[[], ViewTransform] = ViewTransform
        self._viewport_size_px: Callable[[], tuple[float, float]] = lambda: (1.0, 1.0)
        self._drag_origin: tuple[float, float] | None = None

    # ------------------------------------------------------------------ #
    # Host geometry                                                        #
    # ------------------------------------------------------------------ #

    @property
    def host_rect(self) -> QRectF:
        return QRectF(self._host_rect)

    def set_host_rect(self, rect: QRectF) -> None:
        old_bounds = self.bounds()
        self._host_rect = QRectF(rect)
        self._on_host_rect_changed()
        self.request_repaint(old_bounds.union(self.bounds()))

    def _on_host_rect_changed(self) -> None:
        """Hook for subclasses to cascade rect changes into content."""
        return None

    @property
    def content(self) -> CanvasObject | None:
        return self._content

    def set_content(self, content: CanvasObject | None) -> None:
        self._content = content
        self.request_repaint()

    # ------------------------------------------------------------------ #
    # Scene / history services                                             #
    # ------------------------------------------------------------------ #

    def bind_host_services(
        self,
        *,
        scene: Scene2D | None = None,
        command_history: CommandHistory | None = None,
        view_zoom: Callable[[], float] | None = None,
        view_transform: Callable[[], ViewTransform] | None = None,
        viewport_size_px: Callable[[], tuple[float, float]] | None = None,
    ) -> None:
        self._scene = scene
        self._command_history = command_history
        if view_zoom is not None:
            self._view_zoom = view_zoom
        if view_transform is not None:
            self._view_transform = view_transform
        if viewport_size_px is not None:
            self._viewport_size_px = viewport_size_px

    def selection_model(self) -> SelectionModel | None:
        if self._scene is None:
            return None
        return self._scene.selection()

    def command_history(self) -> CommandHistory | None:
        return self._command_history

    def view_zoom(self) -> float:
        return max(1e-6, float(self._view_zoom()))

    def view_transform(self) -> ViewTransform:
        return self._view_transform()

    def viewport_size_px(self) -> tuple[float, float]:
        return self._viewport_size_px()

    def push_command(self, cmd: CanvasCommand, *, already_executed: bool = False) -> None:
        history = self._command_history
        if history is None:
            return
        if already_executed:
            history.push_already_executed(cmd)
        else:
            history.push(cmd)

    # ------------------------------------------------------------------ #
    # Capability attach / detach                                           #
    # ------------------------------------------------------------------ #

    def capabilities(self) -> list[CanvasObjectCapability]:
        return list(self._capabilities)

    def capability_by_id(self, capability_id: str) -> CanvasObjectCapability | None:
        for cap in self._capabilities:
            if cap.capability_id == capability_id:
                return cap
        return None

    def attach(self, cap: CanvasObjectCapability) -> None:
        if any(existing.capability_id == cap.capability_id for existing in self._capabilities):
            raise ValueError(
                f"Capability {cap.capability_id!r} is already attached to {self!r}"
            )
        cap.bind(self)
        self._capabilities.append(cap)
        self.request_repaint()

    def detach(self, capability_id: str) -> None:
        for index, cap in enumerate(self._capabilities):
            if cap.capability_id == capability_id:
                cap.unbind()
                del self._capabilities[index]
                self.request_repaint()
                return
        raise KeyError(f"No capability {capability_id!r} attached to {self!r}")

    # ------------------------------------------------------------------ #
    # Serialization                                                        #
    # ------------------------------------------------------------------ #

    def serialize_capabilities(self) -> dict[str, dict]:
        payload: dict[str, dict] = {}
        for cap in self._capabilities:
            if cap.is_synthesized:
                continue
            payload[cap.capability_id] = {
                "schema_version": cap.schema_version,
                "state": cap.serialize_state(),
            }
        for cap_id, block in self._unknown_capability_blocks.items():
            if cap_id not in payload:
                payload[cap_id] = dict(block)
        return payload

    def load_capabilities(self, payload: dict[str, dict]) -> None:
        for cap_id, block in payload.items():
            cap = self.capability_by_id(cap_id)
            if cap is not None:
                cap.load_state(block.get("state", {}))
            else:
                self._unknown_capability_blocks[cap_id] = dict(block)

    # ------------------------------------------------------------------ #
    # CanvasObject overrides                                               #
    # ------------------------------------------------------------------ #

    def bounds(self) -> AABB:
        rect = self._host_rect
        return AABB(rect.left(), rect.top(), rect.right(), rect.bottom())

    def hit_test(self, world_pt: tuple[float, float]) -> bool:
        """Return whether *world_pt* is inside the host body.

        Capability chrome (e.g. resize handles) uses fixed screen-space hit
        bands and must not expand the host's logical bounds.
        """
        return self.bounds().contains_point(world_pt[0], world_pt[1])

    def paint(self, ctx: CanvasPaintContext) -> None:
        self.paint_host_content(ctx)
        for cap in self._capabilities:
            cap.paint_chrome(ctx)

    def paint_host_content(self, ctx: CanvasPaintContext) -> None:
        if self._content is not None:
            self._content.paint(ctx)

    def handle_input(self, event: CanvasInputEvent) -> bool:
        for cap in reversed(self._capabilities):
            if cap.handle_input(event):
                return True
        if self._content is not None and self._content.handle_input(event):
            return True
        return False

    def on_drag_begin(self, world_pos: tuple[float, float]) -> None:
        self._drag_origin = (self._host_rect.left(), self._host_rect.top())

    def on_drag(self, world_delta: tuple[float, float]) -> None:
        dx, dy = world_delta
        rect = self._host_rect
        self.set_host_rect(
            QRectF(rect.left() + dx, rect.top() + dy, rect.width(), rect.height())
        )

    def on_drag_end(self) -> None:
        self._drag_origin = None


__all__ = ["CapabilityHostObject"]
