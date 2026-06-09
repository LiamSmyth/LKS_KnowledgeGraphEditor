"""Private drag / zoom / rubber-band helpers for :class:`Canvas2DWidget`."""
from __future__ import annotations

import math

from lks_utils.gui_qt.canvas2d.interaction.actions import CANVAS_PAN, CANVAS_PRIMARY, CANVAS_ROTATE
from lks_utils.input import Modifier
from lks_utils.gui_qt.canvas2d.interaction.canvas_commands.command_move_objects import MoveObjectsCommand
from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_rubber_band import RubberBandOverlay
from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform
from lks_utils.spatial.aabb import AABB


class DragControllerMixin:
    """View pan/rotate/zoom, rubber-band, and widget-managed object drag."""

    _MIN_ZOOM: float = 1.0 / 64.0
    _MAX_ZOOM: float = 256.0
    _ZOOM_STEP: float = 1.25
    _ROTATION_SNAP_DEG: float = 15.0

    def _init_drag_controller(self) -> None:
        self._drag_action: str | None = None
        self._drag_screen_anchor: tuple[float, float] | None = None
        self._drag_view_anchor: ViewTransform | None = None
        self._drag_world_anchor: tuple[float, float] | None = None
        self._drag_rotate_reference_angle: float | None = None
        self._rubber_band_overlay: RubberBandOverlay | None = None
        self._rubber_band_screen_start: tuple[float, float] | None = None
        self._rubber_band_subtractive: bool = False
        self._rubber_band_mouse_grabbed: bool = False
        self._dragging_objects: list[CanvasObject] = []
        self._object_drag_screen_prev: tuple[float, float] | None = None
        self._object_drag_world_deltas: dict[int, tuple[float, float]] = {}
        self._zoom_alpha: float = 0.35
        self._pan_alpha: float = 0.5

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

    def _matches_rubber_band_selection(self, obj: CanvasObject, world_aabb: AABB) -> bool:
        """Return whether *obj* should be selected by rubber-band in *world_aabb*.

        Items can implement an optional ``selection_intersects_aabb(world_aabb)``
        method for geometry-accurate overlap checks. If missing, the default
        scene AABB broad-phase match is accepted.
        """
        predicate = getattr(obj, "selection_intersects_aabb", None)
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
                obj
                for obj in self.scene.objects_in_aabb(world_aabb)
                if obj.selectable and self._matches_rubber_band_selection(obj, world_aabb)
            ]
            if hits:
                if getattr(self, "_rubber_band_subtractive", False):
                    self.scene.deselect_objects(hits)
                else:
                    selected_before = self.selected_objects()
                    preferred_active = self.active_selected_object()
                    if not selected_before:
                        preferred_active = hits[0]
                    self.scene.select_objects(
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

    def _begin_object_drag(
        self, objects: list[CanvasObject], screen: tuple[float, float]
    ) -> None:
        """Start a widget-managed drag for *objects*."""
        self._dragging_objects = list(objects)
        self._object_drag_screen_prev = screen
        self._object_drag_world_deltas = {id(obj): (0.0, 0.0) for obj in objects}
        view = self.view()
        viewport = (float(self.width()), float(self.height()))
        wp = view.screen_to_world(screen, viewport)
        for obj in self._dragging_objects:
            obj.on_drag_begin(wp)

    def _handle_object_drag_motion(self, screen: tuple[float, float]) -> None:
        """Update dragged objects as the mouse moves to *screen*."""
        if not self._dragging_objects or self._object_drag_screen_prev is None:
            return
        view = self.view()
        viewport = (float(self.width()), float(self.height()))
        prev_w = view.screen_to_world(self._object_drag_screen_prev, viewport)
        curr_w = view.screen_to_world(screen, viewport)
        dx = curr_w[0] - prev_w[0]
        dy = curr_w[1] - prev_w[1]
        for obj in self._dragging_objects:
            obj.on_drag((dx, dy))
            old_dx, old_dy = self._object_drag_world_deltas[id(obj)]
            self._object_drag_world_deltas[id(obj)] = (old_dx + dx, old_dy + dy)
        self._object_drag_screen_prev = screen
        self.update()

    def _end_object_drag(self) -> None:
        """Finalise the object drag, push a command, and emit `objects_moved`."""
        if not self._dragging_objects:
            return
        for obj in self._dragging_objects:
            obj.on_drag_end()
        deltas = [
            (obj, *self._object_drag_world_deltas[id(obj)])
            for obj in self._dragging_objects
        ]
        moved = list(self._dragging_objects)
        self._dragging_objects = []
        self._object_drag_screen_prev = None
        self._object_drag_world_deltas = {}
        if any(abs(dx) > 1e-9 or abs(dy) > 1e-9 for _, dx, dy in deltas):
            cmd = MoveObjectsCommand(deltas)
            # Register the command in history WITHOUT re-executing it
            # (the drag already applied the deltas live).
            if self.history is not None:
                self.history.push_already_executed(cmd)
            self.objects_moved.emit(moved)
        self.update()