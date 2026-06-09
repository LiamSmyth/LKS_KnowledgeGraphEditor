"""Private Qt input routing for :class:`Canvas2DWidget`."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import (
    QFocusEvent,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QTabletEvent,
    QWheelEvent,
)

from lks_utils.gui_qt.canvas2d.interaction.actions import (
    CANVAS_COPY,
    CANVAS_CUT,
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
    CANVAS_PASTE,
)
from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import (
    CANVAS_OBJECT_KEY,
    CANVAS_OBJECT_WHEEL,
    CANVAS_MOVE,
    CanvasInputEvent,
)
from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.input import GestureKind, Modifier, get_default_bindings
from lks_utils.input.qt_adapter import (
    qt_button_to_logical,
    qt_modifiers_to_logical,
    wheel_event_pair,
)


class InputRoutingMixin:
    """Mouse, wheel, keyboard, and tablet dispatch.

    Composed with :class:`~lks_utils.gui_qt.canvas2d.widgets._drag_controller.DragControllerMixin`
    on ``Canvas2DWidget`` (drag mixin precedes this mixin in the MRO).
    """

    def _init_input_routing(self) -> None:
        self._primary_object: CanvasObject | None = None
        self._key_input_object: CanvasObject | None = None
        self._cursor_screen: tuple[float, float] | None = None
        self._canvas_cursor_override_active: bool = False

    def _schedule_repaint(self) -> None:
        """Request a viewport repaint when canvas pixels may have changed."""
        self.update()

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

    def _route_capability_chrome_press(
        self, event: CanvasInputEvent
    ) -> CanvasObject | None:
        """Route press to selected-object chrome (e.g. resize handles).

        Chrome hit zones are screen-constant and may sit slightly outside the
        host body; they must not expand :meth:`CanvasObject.hit_test`.
        """
        from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability_host import (
            CapabilityHostObject,
        )

        selection = self.scene.selection()
        if selection is None:
            return None
        view = self.camera.view()
        viewport_size_px = (float(self.width()), float(self.height()))
        zoom = max(1e-6, float(view.zoom))
        for obj in reversed(self.scene.objects()):
            if not isinstance(obj, CapabilityHostObject):
                continue
            if not selection.is_selected(obj):
                continue
            for cap in reversed(obj.capabilities()):
                handle_at = getattr(cap, "_handle_at", None)
                if handle_at is None:
                    continue
                handle = handle_at(
                    event.world_pos,
                    zoom=zoom,
                    screen_pos=event.screen_pos,
                    view=view,
                    viewport_size_px=viewport_size_px,
                )
                if handle is None:
                    continue
                if cap.handle_input(event):
                    return obj
        return None

    def _route_to_topmost(
        self, world_pos: tuple[float, float], event: CanvasInputEvent
    ) -> CanvasObject | None:
        """Walk objects top-down; first to consume wins."""
        for obj in reversed(self.scene.objects()):
            if not obj.hit_test(world_pos):
                continue
            if obj.handle_input(event):
                return obj
        return None

    def _topmost_hit_object(self, world_pos: tuple[float, float]) -> CanvasObject | None:
        """Return the topmost object whose precise hit-test contains *world_pos*."""
        for obj in reversed(self.scene.objects()):
            if obj.hit_test(world_pos):
                return obj
        return None

    def _clear_canvas_cursor_override(self) -> None:
        if self._canvas_cursor_override_active:
            QGuiApplication.restoreOverrideCursor()
            self._canvas_cursor_override_active = False

    def _apply_canvas_cursor(self, shape: Qt.CursorShape | None) -> None:
        if shape is None or shape == Qt.CursorShape.ArrowCursor:
            self._clear_canvas_cursor_override()
            return
        if self._canvas_cursor_override_active:
            QGuiApplication.changeOverrideCursor(shape)
            return
        QGuiApplication.setOverrideCursor(shape)
        self._canvas_cursor_override_active = True

    def _cursor_for_world_pos(
        self,
        world_pos: tuple[float, float],
        screen_pos: tuple[float, float] | None = None,
    ) -> Qt.CursorShape | None:
        from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability_host import (
            CapabilityHostObject,
        )

        zoom = max(1e-6, float(self.camera.view().zoom))
        view = self.camera.view()
        viewport_size_px = (float(self.width()), float(self.height()))
        for obj in reversed(self.scene.objects()):
            if not isinstance(obj, CapabilityHostObject):
                continue
            selection = self.scene.selection()
            if selection is None or not selection.is_selected(obj):
                continue
            for cap in reversed(obj.capabilities()):
                cursor = cap.cursor_at(
                    world_pos,
                    zoom=zoom,
                    screen_pos=screen_pos,
                    view=view,
                    viewport_size_px=viewport_size_px,
                )
                if cursor is not None:
                    return cursor
        return None

    def _dispatch_capability_hover_move(
        self,
        world_pos: tuple[float, float],
        screen_pos: tuple[float, float],
        modifiers,
    ) -> None:
        from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability_host import (
            CapabilityHostObject,
        )

        ev = self._make_event(CANVAS_MOVE, "move", screen_pos, modifiers)
        for obj in reversed(self.scene.objects()):
            if not isinstance(obj, CapabilityHostObject):
                continue
            selection = self.scene.selection()
            if selection is None or not selection.is_selected(obj):
                continue
            for cap in reversed(obj.capabilities()):
                cap.handle_input(ev)

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

        # Primary press → topmost object.
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
            consumer = self._route_capability_chrome_press(ev)
            if consumer is None:
                consumer = self._route_to_topmost(wp, ev)
            if consumer is not None:
                # Let object-local interaction (e.g. embedded widget fields,
                # sliders, buttons) win over canvas-level selection.
                self._primary_object = consumer
                self._key_input_object = consumer
                event.accept()
                return

            hit = self._topmost_hit_object(wp)
            is_shift = Modifier.SHIFT in mods
            is_ctrl = Modifier.CTRL in mods

            if self.capabilities.allow_selection:
                if hit is None:
                    self._key_input_object = None
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
                            # Modifier+click on a canvas object toggles it
                            # in/out of selection even when
                            # allow_multi_select is off (legacy behavior).
                            self.toggle_object_selection(hit)
                        elif not self.scene.selection().is_selected(hit):
                            # Plain click on an *unselected* object → replace.
                            # Plain click on an *already-selected* object →
                            # keep the current selection so a multi-drag can
                            # start without clearing it first.
                            self.select_object(hit, additive=False)
                    else:
                        if is_ctrl:
                            self.toggle_object_selection(hit)
                        elif is_shift:
                            # Shift-click is add-only for canvas semantics.
                            self.select_object(hit, additive=True)
                        else:
                            self.select_object(hit, additive=False)

            if (
                self.capabilities.allow_selection
                and self.capabilities.allow_drag
                and hit is not None
                and hit.draggable
            ):
                dragged_objects = [hit]
                if self.scene.selection().is_selected(hit):
                    dragged_objects = [
                        obj
                        for obj in self.selected_objects()
                        if obj.draggable
                    ]
                    if not dragged_objects:
                        dragged_objects = [hit]
                self._begin_object_drag(dragged_objects, screen)
                event.accept()
                return
            # Fallthrough: nothing consumed → fall back to view actions
            # if a view binding matches LMB-press (rare; left empty here).

        # Secondary press → topmost object.
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

        # Active primary object drag?
        if self._primary_object is not None:
            self._clear_hover_tooltip()
            mods = qt_modifiers_to_logical(event.modifiers())
            ev = self._make_event(CANVAS_PRIMARY, "drag", screen, mods)
            self._primary_object.handle_input(ev)
            event.accept()
            return

        # Widget-managed object drag.
        if self._dragging_objects:
            self._clear_hover_tooltip()
            self._handle_object_drag_motion(screen)
            event.accept()
            return

        # Rubber-band drag.
        if self._rubber_band_overlay is not None:
            self._clear_hover_tooltip()
            self._rubber_band_overlay.update_rect(*screen)
            self._schedule_repaint()
            event.accept()
            return

        # Plain hover-move event for items that care.
        mods = qt_modifiers_to_logical(event.modifiers())
        ev = self._make_event(CANVAS_MOVE, "move", screen, mods)
        self._dispatch_capability_hover_move(ev.world_pos, screen, mods)
        self._apply_canvas_cursor(
            self._cursor_for_world_pos(ev.world_pos, screen_pos=screen)
        )
        self._update_hover_tooltip(screen, ev.world_pos)
        self._schedule_repaint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        screen = (event.position().x(), event.position().y())
        mods = qt_modifiers_to_logical(event.modifiers())
        if (
            self._drag_action is not None
            or self._primary_object is not None
            or self._dragging_objects
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
        # Offer the wheel event to the topmost object under the cursor first.
        # Any object whose handle_input returns True consumes the event and
        # prevents the canvas-level zoom gesture from firing.  This lets
        # items with their own scroll behaviour (e.g. a scrollable text area
        # or an embedded scrollbar) override the canvas default.
        ad = event.angleDelta()
        _wheel_ev = self._make_event(
            CANVAS_OBJECT_WHEEL,
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
        if self._key_input_object is not None:
            screen = self._cursor_screen if self._cursor_screen is not None else (
                0.0, 0.0)
            mods = qt_modifiers_to_logical(event.modifiers())
            ev = CanvasInputEvent(
                action=CANVAS_OBJECT_KEY,
                phase="press",
                world_pos=self._screen_to_world(*screen),
                screen_pos=screen,
                modifiers=mods,
                key=int(event.key()),
                text=event.text(),
            )
            if self._key_input_object.handle_input(ev):
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
                for obj in self.objects():
                    self.select_object(obj, additive=True)
            event.accept()
            return
        if bindings.matches_key(CANVAS_DELETE_SELECTED.id, seq):
            if self.capabilities.allow_selection and self.capabilities.allow_add_remove:
                for obj in list(self.selected_objects()):
                    self.remove_object_command(obj)
            event.accept()
            return
        if bindings.matches_key(CANVAS_COPY.id, seq):
            if self.capabilities.allow_clipboard and self.capabilities.allow_selection:
                self._clipboard = list(self.selected_objects())
            event.accept()
            return
        if bindings.matches_key(CANVAS_CUT.id, seq):
            if self.capabilities.allow_clipboard and self.capabilities.allow_selection and self.capabilities.allow_add_remove:
                self._clipboard = list(self.selected_objects())
                for obj in self._clipboard:
                    self.remove_object_command(obj)
                self.clear_selection()
            event.accept()
            return
        if bindings.matches_key(CANVAS_PASTE.id, seq):
            if self.capabilities.allow_clipboard and self.capabilities.allow_add_remove and self._clipboard:
                if self.object_clone_fn is not None:
                    self.clear_selection()
                    for src in self._clipboard:
                        clone = self.object_clone_fn(src)
                        if clone is None:
                            continue
                        self.add_object_command(clone)
                        self.select_object(clone, additive=True)
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
        if self._key_input_object is not None:
            screen = self._cursor_screen if self._cursor_screen is not None else (
                0.0, 0.0)
            mods = qt_modifiers_to_logical(event.modifiers())
            ev = CanvasInputEvent(
                action=CANVAS_OBJECT_KEY,
                phase="release",
                world_pos=self._screen_to_world(*screen),
                screen_pos=screen,
                modifiers=mods,
                key=int(event.key()),
                text=event.text(),
            )
            if self._key_input_object.handle_input(ev):
                event.accept()
                return
        super().keyReleaseEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._cursor_screen = None
        self._clear_canvas_cursor_override()
        self._clear_hover_tooltip()
        self.update()
        super().leaveEvent(event)

    def _end_pointer_interactions(
        self,
        screen: tuple[float, float] | None,
        mods: frozenset[Modifier],
        *,
        commit_rubber_band: bool,
    ) -> None:
        """End all pointer-driven transient states.

        Owns primary-object release; delegates view/object drag and rubber-band
        cleanup to :class:`~lks_utils.gui_qt.canvas2d.widgets._drag_controller.DragControllerMixin`.
        """
        release_screen = screen if screen is not None else (0.0, 0.0)
        if self._drag_action is not None:
            self._end_drag(release_screen)
        if self._primary_object is not None:
            primary_object = self._primary_object
            self._primary_object = None
            ev = self._make_event(
                CANVAS_PRIMARY, "release", release_screen, mods)
            primary_object.handle_input(ev)
        if self._dragging_objects:
            self._end_object_drag()
        if self._rubber_band_overlay is not None:
            if commit_rubber_band:
                self._end_rubber_band()
            else:
                self._cancel_rubber_band()

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
                self._primary_object = consumer
                self._key_input_object = consumer
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

            # Active primary object drag (pen tip painting).
            if self._primary_object is not None:
                ev = self._make_event(
                    CANVAS_PRIMARY, "drag", screen, mods,
                    pressure=float(event.pressure()), is_tablet=True,
                )
                self._primary_object.handle_input(ev)
                event.accept()
                return

            self._schedule_repaint()

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
            if self._primary_object is not None:
                ev = self._make_event(
                    CANVAS_PRIMARY, "release", screen, mods,
                    pressure=float(event.pressure()), is_tablet=True,
                )
                self._primary_object.handle_input(ev)
                self._primary_object = None
                event.accept()
                return

        super().tabletEvent(event)
