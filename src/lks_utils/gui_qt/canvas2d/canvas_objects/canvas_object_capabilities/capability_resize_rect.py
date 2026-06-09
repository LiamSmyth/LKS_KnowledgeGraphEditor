"""ResizeRectCapability — rectangular resize handles with live preview."""
from __future__ import annotations

import math
from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability import CanvasObjectCapability
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_node import CanvasNodeSizeMode
from lks_utils.gui_qt.canvas2d.interaction.actions import CANVAS_PRIMARY
from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CANVAS_OBJECT_KEY
if TYPE_CHECKING:
    from PySide6.QtCore import QRectF

    from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform
    from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CanvasInputEvent
    from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext


class HandleId(str, Enum):
    TOP_LEFT = "top_left"
    TOP = "top"
    TOP_RIGHT = "top_right"
    RIGHT = "right"
    BOTTOM_RIGHT = "bottom_right"
    BOTTOM = "bottom"
    BOTTOM_LEFT = "bottom_left"
    LEFT = "left"


_HandleId = HandleId

_CORNER_HANDLES = frozenset({
    _HandleId.TOP_LEFT,
    _HandleId.TOP_RIGHT,
    _HandleId.BOTTOM_LEFT,
    _HandleId.BOTTOM_RIGHT,
})
_EDGE_HANDLES = frozenset({
    _HandleId.TOP,
    _HandleId.BOTTOM,
    _HandleId.LEFT,
    _HandleId.RIGHT,
})
_OPPOSITE_CORNER: dict[_HandleId, _HandleId] = {
    _HandleId.TOP_LEFT: _HandleId.BOTTOM_RIGHT,
    _HandleId.TOP_RIGHT: _HandleId.BOTTOM_LEFT,
    _HandleId.BOTTOM_LEFT: _HandleId.TOP_RIGHT,
    _HandleId.BOTTOM_RIGHT: _HandleId.TOP_LEFT,
}


class ResizeRectCapability(CanvasObjectCapability):
    """Resize host rect via handles; commits :class:`ResizeObjectCommand`."""

    capability_id = "resize_rect"
    schema_version = 1

    _CORNER_HIT_RADIUS_PX: float = 8.0
    _EDGE_HIT_THICKNESS_PX: float = 8.0

    _EDGE_CURSOR: dict[_HandleId, Qt.CursorShape] = {
        _HandleId.TOP: Qt.CursorShape.SizeVerCursor,
        _HandleId.BOTTOM: Qt.CursorShape.SizeVerCursor,
        _HandleId.LEFT: Qt.CursorShape.SizeHorCursor,
        _HandleId.RIGHT: Qt.CursorShape.SizeHorCursor,
    }

    def __init__(
        self,
        *,
        min_size: tuple[float, float] = (32.0, 32.0),
        max_size: tuple[float, float] | None = None,
        enabled_handles: frozenset[HandleId] = frozenset(HandleId),
    ) -> None:
        super().__init__()
        self._min_w, self._min_h = min_size
        self._max_w = max_size[0] if max_size else None
        self._max_h = max_size[1] if max_size else None
        self._enabled_handles = frozenset(enabled_handles)
        self._active_handle: _HandleId | None = None
        self._preview_active = False
        self._preview_start_rect: QRectF | None = None
        self._last_world_pos: tuple[float, float] | None = None
        self._hover_handle: _HandleId | None = None

    def _is_selected(self) -> bool:
        host = self._host
        if host is None:
            return False
        selection = host.selection_model()
        return selection is not None and selection.is_selected(host)

    def hit_test_chrome(
        self,
        world_pos: tuple[float, float],
        *,
        zoom: float,
        screen_pos: tuple[float, float] | None = None,
        view: ViewTransform | None = None,
        viewport_size_px: tuple[float, float] | None = None,
    ) -> bool:
        if not self._is_selected():
            return False
        return self._handle_at(
            world_pos,
            zoom=zoom,
            screen_pos=screen_pos,
            view=view,
            viewport_size_px=viewport_size_px,
        ) is not None

    def cursor_at(
        self,
        world_pos: tuple[float, float],
        *,
        zoom: float,
        screen_pos: tuple[float, float] | None = None,
        view: ViewTransform | None = None,
        viewport_size_px: tuple[float, float] | None = None,
    ) -> Qt.CursorShape | None:
        if not self._is_selected():
            return None
        handle = self._handle_at(
            world_pos,
            zoom=zoom,
            screen_pos=screen_pos,
            view=view,
            viewport_size_px=viewport_size_px,
        )
        if handle is None:
            return None
        return self._cursor_for_handle(handle, view=view, viewport_size_px=viewport_size_px)

    def handle_input(self, event: CanvasInputEvent) -> bool:
        host = self._host
        if host is None:
            return False

        if event.action.id == CANVAS_OBJECT_KEY.id and event.phase == "press":
            if event.key == int(Qt.Key.Key_Escape) and self._preview_active:
                self.cancel_preview()
                host.request_repaint()
                return True
            return False

        if event.action.id != CANVAS_PRIMARY.id:
            return False

        view = host.view_transform()
        viewport_size_px = host.viewport_size_px()

        if event.phase == "move":
            zoom = host.view_zoom()
            self._hover_handle = self._handle_at(
                event.world_pos,
                zoom=zoom,
                screen_pos=event.screen_pos,
                view=view,
                viewport_size_px=viewport_size_px,
            )
            return False

        if event.phase == "press":
            handle = self._handle_at(
                event.world_pos,
                zoom=host.view_zoom(),
                screen_pos=event.screen_pos,
                view=view,
                viewport_size_px=viewport_size_px,
            )
            if handle is None:
                return False
            self._active_handle = handle
            self._last_world_pos = event.world_pos
            self.begin_preview()
            return True

        if not self._preview_active or self._active_handle is None:
            return False

        if event.phase == "drag":
            if self._last_world_pos is not None:
                dx = event.world_pos[0] - self._last_world_pos[0]
                dy = event.world_pos[1] - self._last_world_pos[1]
                self._apply_handle_delta(dx, dy)
            self._last_world_pos = event.world_pos
            host.request_repaint()
            return True

        if event.phase == "release":
            self._active_handle = None
            self._last_world_pos = None
            cmd = self.commit()
            if cmd is not None:
                host.push_command(cmd, already_executed=True)
            host.request_repaint()
            return True

        return False

    def paint_chrome(self, ctx: CanvasPaintContext) -> None:
        """Resize affordance is cursor-only; no on-canvas handle geometry."""

    def serialize_state(self) -> dict:
        host = self._host
        if host is None:
            return {}
        rect = host.host_rect
        size_mode = getattr(host, "size_mode", CanvasNodeSizeMode.USER_OVERRIDE)
        mode_value = size_mode.value if hasattr(size_mode, "value") else str(size_mode)
        return {
            "host_rect": {
                "x": rect.left(),
                "y": rect.top(),
                "w": rect.width(),
                "h": rect.height(),
            },
            "size_mode": mode_value,
            "constraints": {
                "min_w": self._min_w,
                "min_h": self._min_h,
                "max_w": self._max_w,
                "max_h": self._max_h,
            },
            "enabled_handles": sorted(handle.value for handle in self._enabled_handles),
        }

    def load_state(self, payload: dict) -> None:
        host = self._host
        if host is None:
            return
        from PySide6.QtCore import QRectF

        host_rect = payload.get("host_rect")
        if isinstance(host_rect, dict):
            host.set_host_rect(
                QRectF(
                    float(host_rect.get("x", 0.0)),
                    float(host_rect.get("y", 0.0)),
                    float(host_rect.get("w", 1.0)),
                    float(host_rect.get("h", 1.0)),
                )
            )
        size_mode = payload.get("size_mode")
        if size_mode is not None and hasattr(host, "size_mode"):
            try:
                host.size_mode = CanvasNodeSizeMode(str(size_mode))
            except ValueError:
                pass
        constraints = payload.get("constraints", {})
        if isinstance(constraints, dict):
            self._min_w = float(constraints.get("min_w", self._min_w))
            self._min_h = float(constraints.get("min_h", self._min_h))
            max_w = constraints.get("max_w")
            max_h = constraints.get("max_h")
            self._max_w = float(max_w) if max_w is not None else None
            self._max_h = float(max_h) if max_h is not None else None
        enabled_handles = payload.get("enabled_handles")
        if isinstance(enabled_handles, list):
            self._enabled_handles = frozenset(
                HandleId(str(handle_id)) for handle_id in enabled_handles
            )

    def begin_preview(self) -> None:
        host = self._host
        if host is None:
            return
        self._preview_start_rect = host.host_rect
        self._preview_active = True
        if hasattr(host, "size_mode"):
            host.size_mode = CanvasNodeSizeMode.USER_OVERRIDE

    def cancel_preview(self) -> None:
        host = self._host
        if host is None:
            return
        if self._preview_start_rect is not None:
            host.set_host_rect(self._preview_start_rect)
        self._preview_start_rect = None
        self._preview_active = False
        self._active_handle = None
        self._last_world_pos = None

    def commit(self):
        from lks_utils.gui_qt.canvas2d.interaction.canvas_commands.command_resize_object import (
            ResizeObjectCommand,
        )

        host = self._host
        if host is None or self._preview_start_rect is None:
            return None
        start = self._preview_start_rect
        end = host.host_rect
        self._preview_start_rect = None
        self._preview_active = False
        if (
            abs(start.left() - end.left()) < 1e-9
            and abs(start.top() - end.top()) < 1e-9
            and abs(start.width() - end.width()) < 1e-9
            and abs(start.height() - end.height()) < 1e-9
        ):
            return None
        return ResizeObjectCommand(host, start, end)

    @staticmethod
    def _south_y(rect: QRectF) -> float:
        return rect.top()

    @staticmethod
    def _north_y(rect: QRectF) -> float:
        return rect.bottom()

    def _visual_corner_screen_points(
        self,
        rect: QRectF,
        view: ViewTransform,
        viewport_size_px: tuple[float, float],
    ) -> dict[_HandleId, tuple[float, float]]:
        south = self._south_y(rect)
        north = self._north_y(rect)
        return {
            _HandleId.TOP_LEFT: view.world_to_screen((rect.left(), south), viewport_size_px),
            _HandleId.TOP_RIGHT: view.world_to_screen((rect.right(), south), viewport_size_px),
            _HandleId.BOTTOM_LEFT: view.world_to_screen((rect.left(), north), viewport_size_px),
            _HandleId.BOTTOM_RIGHT: view.world_to_screen((rect.right(), north), viewport_size_px),
        }

    @staticmethod
    def _edge_screen_segments(
        corners: dict[_HandleId, tuple[float, float]],
    ) -> dict[_HandleId, tuple[tuple[float, float], tuple[float, float]]]:
        return {
            _HandleId.TOP: (corners[_HandleId.TOP_LEFT], corners[_HandleId.TOP_RIGHT]),
            _HandleId.BOTTOM: (corners[_HandleId.BOTTOM_LEFT], corners[_HandleId.BOTTOM_RIGHT]),
            _HandleId.LEFT: (corners[_HandleId.TOP_LEFT], corners[_HandleId.BOTTOM_LEFT]),
            _HandleId.RIGHT: (corners[_HandleId.TOP_RIGHT], corners[_HandleId.BOTTOM_RIGHT]),
        }

    @staticmethod
    def _distance_to_screen_segment(
        px: float,
        py: float,
        a: tuple[float, float],
        b: tuple[float, float],
    ) -> float:
        ax, ay = a
        bx, by = b
        dx = bx - ax
        dy = by - ay
        len2 = dx * dx + dy * dy
        if len2 < 1e-12:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len2))
        cx = ax + t * dx
        cy = ay + t * dy
        return math.hypot(px - cx, py - cy)

    def _cursor_for_handle(
        self,
        handle_id: _HandleId,
        *,
        view: ViewTransform | None,
        viewport_size_px: tuple[float, float] | None,
    ) -> Qt.CursorShape | None:
        if handle_id in _EDGE_HANDLES:
            return self._EDGE_CURSOR.get(handle_id)
        if handle_id not in _CORNER_HANDLES:
            return None
        host = self._host
        if host is None or view is None or viewport_size_px is None:
            return Qt.CursorShape.SizeFDiagCursor
        rect = host.host_rect
        opposite = _OPPOSITE_CORNER[handle_id]
        corners = self._visual_corner_screen_points(rect, view, viewport_size_px)
        sx0, sy0 = corners[opposite]
        sx1, sy1 = corners[handle_id]
        dx = sx1 - sx0
        dy = sy1 - sy0
        if dx * dy >= 0.0:
            return Qt.CursorShape.SizeFDiagCursor
        return Qt.CursorShape.SizeBDiagCursor

    def _handle_at(
        self,
        world_pos: tuple[float, float],
        *,
        zoom: float,
        screen_pos: tuple[float, float] | None = None,
        view: ViewTransform | None = None,
        viewport_size_px: tuple[float, float] | None = None,
    ) -> _HandleId | None:
        host = self._host
        if host is None:
            return None
        rect = host.host_rect

        viewport_w, viewport_h = viewport_size_px or (0.0, 0.0)
        use_screen_hit = (
            screen_pos is not None
            and view is not None
            and viewport_size_px is not None
            and viewport_w > 16.0
            and viewport_h > 16.0
        )
        if use_screen_hit:
            return self._handle_at_screen(screen_pos, rect, view, viewport_size_px)

        return self._handle_at_world(world_pos, rect, zoom=zoom)

    def _handle_at_screen(
        self,
        screen_pos: tuple[float, float],
        rect: QRectF,
        view: ViewTransform,
        viewport_size_px: tuple[float, float],
    ) -> _HandleId | None:
        sx, sy = screen_pos
        corners = self._visual_corner_screen_points(rect, view, viewport_size_px)
        corner_hit_radius = self._CORNER_HIT_RADIUS_PX
        best_corner: _HandleId | None = None
        best_corner_dist = corner_hit_radius
        for handle_id in _CORNER_HANDLES:
            if handle_id not in self._enabled_handles:
                continue
            cx, cy = corners[handle_id]
            dist = math.hypot(sx - cx, sy - cy)
            if dist <= best_corner_dist:
                best_corner = handle_id
                best_corner_dist = dist

        if best_corner is not None:
            return best_corner

        edge_segments = self._edge_screen_segments(corners)
        half_hit = self._EDGE_HIT_THICKNESS_PX * 0.5
        best_edge: _HandleId | None = None
        best_edge_dist = half_hit
        for handle_id, segment in edge_segments.items():
            if handle_id not in self._enabled_handles:
                continue
            dist = self._distance_to_screen_segment(sx, sy, segment[0], segment[1])
            if dist <= best_edge_dist:
                best_edge = handle_id
                best_edge_dist = dist
        return best_edge

    def _handle_at_world(
        self,
        world_pos: tuple[float, float],
        rect: QRectF,
        *,
        zoom: float,
    ) -> _HandleId | None:
        hit_radius_world = self._CORNER_HIT_RADIUS_PX / max(1e-6, float(zoom))
        hit_r2 = hit_radius_world * hit_radius_world
        corners = {
            handle_id: position
            for handle_id, position in self._corner_world_positions(rect).items()
            if handle_id in self._enabled_handles
        }
        best: _HandleId | None = None
        best_dist = hit_r2
        for handle_id, (wx, wy) in corners.items():
            dist_wx = world_pos[0] - wx
            dist_wy = world_pos[1] - wy
            dist2 = dist_wx * dist_wx + dist_wy * dist_wy
            if dist2 <= hit_r2 and dist2 <= best_dist:
                best = handle_id
                best_dist = dist2
        if best is not None:
            return best

        half_hit_world = (self._EDGE_HIT_THICKNESS_PX * 0.5) / max(1e-6, float(zoom))
        south = self._south_y(rect)
        north = self._north_y(rect)
        wx, wy = world_pos
        edge_candidates: list[tuple[_HandleId, float]] = []
        if _HandleId.TOP in self._enabled_handles and rect.left() <= wx <= rect.right():
            edge_candidates.append((_HandleId.TOP, abs(wy - south)))
        if _HandleId.BOTTOM in self._enabled_handles and rect.left() <= wx <= rect.right():
            edge_candidates.append((_HandleId.BOTTOM, abs(wy - north)))
        if _HandleId.LEFT in self._enabled_handles and south <= wy <= north:
            edge_candidates.append((_HandleId.LEFT, abs(wx - rect.left())))
        if _HandleId.RIGHT in self._enabled_handles and south <= wy <= north:
            edge_candidates.append((_HandleId.RIGHT, abs(wx - rect.right())))

        edge_best: _HandleId | None = None
        edge_best_dist = half_hit_world
        for handle_id, dist in edge_candidates:
            if dist <= edge_best_dist:
                edge_best = handle_id
                edge_best_dist = dist
        return edge_best

    @staticmethod
    def _corner_world_positions(rect: QRectF) -> dict[_HandleId, tuple[float, float]]:
        south = ResizeRectCapability._south_y(rect)
        north = ResizeRectCapability._north_y(rect)
        return {
            _HandleId.TOP_LEFT: (rect.left(), south),
            _HandleId.TOP_RIGHT: (rect.right(), south),
            _HandleId.BOTTOM_LEFT: (rect.left(), north),
            _HandleId.BOTTOM_RIGHT: (rect.right(), north),
        }

    def _handle_positions(self, rect: QRectF) -> dict[_HandleId, tuple[float, float]]:
        south = self._south_y(rect)
        north = self._north_y(rect)
        cx = (rect.left() + rect.right()) * 0.5
        cy = (south + north) * 0.5
        positions = {
            _HandleId.TOP_LEFT: (rect.left(), south),
            _HandleId.TOP_RIGHT: (rect.right(), south),
            _HandleId.BOTTOM_LEFT: (rect.left(), north),
            _HandleId.BOTTOM_RIGHT: (rect.right(), north),
            _HandleId.TOP: (cx, south),
            _HandleId.BOTTOM: (cx, north),
            _HandleId.LEFT: (rect.left(), cy),
            _HandleId.RIGHT: (rect.right(), cy),
        }
        return {
            handle_id: position
            for handle_id, position in positions.items()
            if handle_id in self._enabled_handles
        }

    def _apply_handle_delta(self, dx: float, dy: float) -> None:
        host = self._host
        handle = self._active_handle
        if host is None or handle is None:
            return
        from PySide6.QtCore import QRectF

        rect = host.host_rect
        left = rect.left()
        right = rect.right()
        top = rect.top()
        bottom = rect.bottom()

        if handle in {_HandleId.TOP_LEFT, _HandleId.LEFT, _HandleId.BOTTOM_LEFT}:
            left += dx
        if handle in {_HandleId.TOP_RIGHT, _HandleId.RIGHT, _HandleId.BOTTOM_RIGHT}:
            right += dx
        if handle in {_HandleId.TOP_LEFT, _HandleId.TOP, _HandleId.TOP_RIGHT}:
            top += dy
        if handle in {_HandleId.BOTTOM_LEFT, _HandleId.BOTTOM, _HandleId.BOTTOM_RIGHT}:
            bottom += dy

        width = right - left
        height = bottom - top
        if width < self._min_w:
            if handle in {_HandleId.TOP_LEFT, _HandleId.LEFT, _HandleId.BOTTOM_LEFT}:
                left = right - self._min_w
            else:
                right = left + self._min_w
            width = self._min_w
        if height < self._min_h:
            if handle in {_HandleId.TOP_LEFT, _HandleId.TOP, _HandleId.TOP_RIGHT}:
                top = bottom - self._min_h
            else:
                bottom = top + self._min_h
            height = self._min_h
        if self._max_w is not None and width > self._max_w:
            if handle in {_HandleId.TOP_LEFT, _HandleId.LEFT, _HandleId.BOTTOM_LEFT}:
                left = right - self._max_w
            else:
                right = left + self._max_w
        if self._max_h is not None and height > self._max_h:
            if handle in {_HandleId.TOP_LEFT, _HandleId.TOP, _HandleId.TOP_RIGHT}:
                top = bottom - self._max_h
            else:
                bottom = top + self._max_h

        host.set_host_rect(QRectF(left, top, right - left, bottom - top))


__all__ = ["HandleId", "ResizeRectCapability"]
