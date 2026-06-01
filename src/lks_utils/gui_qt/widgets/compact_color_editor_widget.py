"""Compact color editor widget with hue wheel, SV square, and swatch presets."""
from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QMimeData, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QFontDatabase, QGuiApplication, QIcon, QImage, QMouseEvent, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.widgets._modifier_slider import _ModifierSlider
from lks_utils.gui_qt.theme.icon_recolor import recolor_svg


_MIME_COLOR = "application/x-lks-color-rgba"
_PRESET_EXTENSION = ".json"


def _repo_root_from_widget_file() -> Path:
    return Path(__file__).resolve().parents[4]


def _gui_qt_data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data"


def _themed_data_icon(svg_name: str, color_hex: str) -> QIcon | None:
    icon_path = _gui_qt_data_dir() / svg_name
    if not icon_path.exists():
        return None
    try:
        raw_svg = icon_path.read_text(encoding="utf-8")
        recolored = recolor_svg(raw_svg, fill=color_hex, stroke=color_hex)
        pixmap = QPixmap()
        loaded = pixmap.loadFromData(
            QByteArray(recolored.encode("utf-8")), "SVG")
        if not loaded or pixmap.isNull():
            return QIcon(str(icon_path))
        return QIcon(pixmap)
    except Exception:
        return QIcon(str(icon_path))


def _icon_color_for_background(background: QColor) -> str:
    # Perceived luminance using sRGB coefficients.
    luminance = (0.2126 * background.red()) + (0.7152 *
                                               background.green()) + (0.0722 * background.blue())
    return "#f4f4f4" if luminance < 128.0 else "#101010"


def _sample_screen_pixel(global_pos: QPoint) -> QColor | None:
    screen = QGuiApplication.screenAt(global_pos)
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is None:
        return None
    shot = screen.grabWindow(0, global_pos.x(), global_pos.y(), 1, 1)
    if shot.isNull():
        return None
    image = shot.toImage()
    if image.isNull() or image.width() < 1 or image.height() < 1:
        return None
    return image.pixelColor(0, 0)


def _clamp_255(value: int) -> int:
    return max(0, min(255, int(value)))


def _get_mono_font() -> QFont | None:
    installed_families = set(QFontDatabase.families())
    candidates = [
        "Consolas",
        "Cascadia Mono",
        "Cascadia Code",
        "Courier New",
        "DejaVu Sans Mono",
        "Liberation Mono",
    ]
    chosen = next(
        (family for family in candidates if family in installed_families), None)
    if chosen is None:
        return None
    return QFont(chosen)


def _color_to_payload(color: QColor) -> str:
    return f"{color.red()},{color.green()},{color.blue()},{color.alpha()}"


def _payload_to_color(payload: str) -> QColor | None:
    parts = payload.strip().split(",")
    if len(parts) != 4:
        return None
    try:
        r, g, b, a = [_clamp_255(int(p)) for p in parts]
    except ValueError:
        return None
    return QColor(r, g, b, a)


class _CurrentColorSwatch(QFrame):
    """Top-left current color swatch draggable into palette sockets."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setFrameShape(QFrame.Shape.Panel)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._color = QColor(255, 255, 255, 255)
        self._drag_start = QPointF(0.0, 0.0)

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._color)
        painter.end()

    # type: ignore[override]
    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._drag_start = event.position()

    # type: ignore[override]
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (event.position() - self._drag_start).manhattanLength() < 8:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_MIME_COLOR, _color_to_payload(
            self._color).encode("utf-8"))
        drag.setMimeData(mime)
        pixmap = QPixmap(self.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.fillRect(pixmap.rect(), self._color)
        p.end()
        drag.setPixmap(pixmap)
        drag.exec(Qt.DropAction.CopyAction)


class _PaletteSocket(QFrame):
    """Single drop target for swatch colors."""

    color_changed = Signal(int, object)  # index, QColor
    clicked = Signal(int)

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = index
        self._color: QColor | None = None
        self.setFixedSize(22, 22)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.Box)
        self.setLineWidth(1)

    def color(self) -> QColor | None:
        return QColor(self._color) if self._color is not None else None

    def set_color(self, color: QColor | None) -> None:
        self._color = QColor(color) if color is not None else None
        self.update()
        if self._color is not None:
            self.color_changed.emit(self._index, QColor(self._color))

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(30, 30, 30))
        if self._color is None:
            pen = QPen(QColor(95, 95, 95))
            pen.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(pen)
            painter.drawRect(self.rect().adjusted(2, 2, -3, -3))
        else:
            painter.fillRect(self.rect().adjusted(2, 2, -2, -2), self._color)
        painter.end()

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat(_MIME_COLOR):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        payload = bytes(event.mimeData().data(_MIME_COLOR)).decode("utf-8")
        color = _payload_to_color(payload)
        if color is None:
            return
        self.set_color(color)
        event.acceptProposedAction()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._index)
            event.accept()
            return
        super().mousePressEvent(event)


class _ColorSliderRow(QWidget):
    """Label + slider + fixed-width numeric value."""

    value_changed = Signal(int)

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._label = QLabel(label)
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._label.setFixedWidth(10)
        mono_font = _get_mono_font()
        if mono_font is not None:
            self._label.setFont(mono_font)
        layout.addWidget(self._label)

        self._slider = _ModifierSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 255)
        self._slider.setFixedHeight(14)
        self._slider.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._slider.valueChanged.connect(self.value_changed)
        layout.addWidget(self._slider, 1)

        self._value_label = QLabel("0")
        self._value_label.setFixedWidth(26)
        self._value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if mono_font is not None:
            self._value_label.setFont(mono_font)
        layout.addWidget(self._value_label)

        self._slider.valueChanged.connect(self._on_value_changed)

    def set_label(self, text: str) -> None:
        self._label.setText(text)

    def set_value(self, value: int) -> None:
        self._slider.setValue(_clamp_255(value))

    def value(self) -> int:
        return int(self._slider.value())

    def set_enabled(self, enabled: bool) -> None:
        self._slider.setEnabled(enabled)

    def _set_gradient_style(self, start: QColor, end: QColor) -> None:
        self._slider.setStyleSheet(
            f"QSlider::groove:horizontal {{"
            f"height: 8px;"
            f"border: 1px solid rgb(44,44,44);"
            f"border-radius: 0px;"
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 rgba({start.red()},{start.green()},{start.blue()},{start.alpha()}), "
            f"stop:1 rgba({end.red()},{end.green()},{end.blue()},{end.alpha()}));"
            f"}}"
            f"QSlider::handle:horizontal {{"
            f"background: rgb(220,220,220);"
            f"border: 1px solid rgb(32,32,32);"
            f"width: 8px;"
            f"margin: -1px 0;"
            f"border-radius: 4px;"
            f"}}"
        )

    def set_alpha_style(self, enabled: bool) -> None:
        if enabled:
            self._slider.setStyleSheet(
                "QSlider::groove:horizontal {"
                "height: 8px;"
                "border: 1px solid rgb(44,44,44);"
                "border-radius: 0px;"
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgb(0,0,0), stop:1 rgb(255,255,255));"
                "}"
                "QSlider::handle:horizontal {"
                "background: rgb(220,220,220);"
                "border: 1px solid rgb(32,32,32);"
                "width: 8px;"
                "margin: -1px 0;"
                "border-radius: 4px;"
                "}"
            )
        else:
            self._slider.setStyleSheet("")

    def set_alpha_color_style(self, base_color: QColor) -> None:
        transparent = QColor(
            base_color.red(), base_color.green(), base_color.blue(), 0)
        opaque = QColor(base_color.red(), base_color.green(),
                        base_color.blue(), 255)
        self._set_gradient_style(transparent, opaque)

    def set_hue_style(self) -> None:
        """Set hue gradient as full-saturation/full-value rainbow."""
        self._slider.setStyleSheet(
            "QSlider::groove:horizontal {"
            "height: 8px;"
            "border-radius: 0px;"
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {QColor.fromHsv(0, 255, 255).name()}, "
            f"stop:0.17 {QColor.fromHsv(60, 255, 255).name()}, "
            f"stop:0.33 {QColor.fromHsv(120, 255, 255).name()}, "
            f"stop:0.5 {QColor.fromHsv(180, 255, 255).name()}, "
            f"stop:0.67 {QColor.fromHsv(240, 255, 255).name()}, "
            f"stop:0.83 {QColor.fromHsv(300, 255, 255).name()}, "
            f"stop:1 {QColor.fromHsv(359, 255, 255).name()});"
            "}"
            "QSlider::handle:horizontal {"
            "background: rgb(220,220,220);"
            "border: 1px solid rgb(32,32,32);"
            "width: 8px;"
            "margin: -1px 0;"
            "border-radius: 4px;"
            "}"
        )

    def set_saturation_style(self, *, hue: int, val: int) -> None:
        """Set saturation gradient synced to current hue/value."""
        start = QColor.fromHsv(hue, 0, val)
        end = QColor.fromHsv(hue, 255, val)
        self._set_gradient_style(start, end)

    def set_value_style(self, *, hue: int, sat: int) -> None:
        """Set value gradient synced to current hue/saturation."""
        start = QColor.fromHsv(hue, sat, 0)
        end = QColor.fromHsv(hue, sat, 255)
        self._set_gradient_style(start, end)

    def set_red_style(self, *, g: int, b: int, a: int = 255) -> None:
        """Set red channel gradient while keeping G/B fixed."""
        start = QColor(0, _clamp_255(g), _clamp_255(b), _clamp_255(a))
        end = QColor(255, _clamp_255(g), _clamp_255(b), _clamp_255(a))
        self._set_gradient_style(start, end)

    def set_green_style(self, *, r: int, b: int, a: int = 255) -> None:
        """Set green channel gradient while keeping R/B fixed."""
        start = QColor(_clamp_255(r), 0, _clamp_255(b), _clamp_255(a))
        end = QColor(_clamp_255(r), 255, _clamp_255(b), _clamp_255(a))
        self._set_gradient_style(start, end)

    def set_blue_style(self, *, r: int, g: int, a: int = 255) -> None:
        """Set blue channel gradient while keeping R/G fixed."""
        start = QColor(_clamp_255(r), _clamp_255(g), 0, _clamp_255(a))
        end = QColor(_clamp_255(r), _clamp_255(g), 255, _clamp_255(a))
        self._set_gradient_style(start, end)

    def _on_value_changed(self, value: int) -> None:
        self._value_label.setText(str(value))


class _HueSatValPicker(QWidget):
    """Hue wheel + center saturation-value square picker."""

    color_changed = Signal(object)  # QColor

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(220, 220)
        self._hue_255 = 0
        self._sat_255 = 255
        self._val_255 = 255
        self._drag_mode = ""
        self._mouse_captured = False
        self._cached_wheel_image: QImage | None = None
        self._cached_wheel_size = (0, 0)
        self._cached_sv_image: QImage | None = None
        self._cached_sv_size = (0, 0)
        self._cached_sv_hue = -1

    def set_hsva(self, hue_255: int, sat_255: int, val_255: int) -> None:
        self._hue_255 = _clamp_255(hue_255)
        self._sat_255 = _clamp_255(sat_255)
        self._val_255 = _clamp_255(val_255)
        self.update()

    def hsva(self) -> tuple[int, int, int]:
        return self._hue_255, self._sat_255, self._val_255

    def _ring_geometry(self) -> tuple[QPointF, float, float]:
        side = min(self.width(), self.height())
        cx = self.width() * 0.5
        cy = self.height() * 0.5
        outer = side * 0.48
        thickness = max(8.0, side * 0.045)
        inner = max(0.0, outer - thickness)
        return QPointF(cx, cy), inner, outer

    def _sv_rect(self) -> QRectF:
        center, inner, _ = self._ring_geometry()
        # Fit the SV square by diagonal so its corners always remain inside the inner ring.
        gap = 2.0
        half = max(4.0, (inner - gap) / math.sqrt(2.0))
        return QRectF(center.x() - half, center.y() - half, half * 2.0, half * 2.0)

    def _color_from_hsv(self, h: int, s: int, v: int) -> QColor:
        hue_deg = int(round((h / 255.0) * 359.0))
        return QColor.fromHsv(hue_deg, _clamp_255(s), _clamp_255(v), 255)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        center, inner, outer = self._ring_geometry()
        ring_thickness = max(1.0, outer - inner)
        ring_rect = QRectF(
            center.x() - outer,
            center.y() - outer,
            outer * 2.0,
            outer * 2.0,
        )

        # Render hue wheel using the same atan2-based hue mapping as pointer picking.
        # This guarantees ring colors and marker position stay in sync.
        wheel_size = (int(ring_rect.width()), int(ring_rect.height()))
        if self._cached_wheel_image is None or self._cached_wheel_size != wheel_size:
            wheel_image = QImage(
                wheel_size[0],
                wheel_size[1],
                QImage.Format.Format_ARGB32,
            )
            wheel_image.fill(Qt.GlobalColor.transparent)

            center_x = (wheel_size[0] - 1) * 0.5
            center_y = (wheel_size[1] - 1) * 0.5
            aa_band = 1.25

            for y in range(wheel_size[1]):
                for x in range(wheel_size[0]):
                    dx = x - center_x
                    dy = y - center_y
                    dist = math.hypot(dx, dy)
                    if dist < (inner - aa_band) or dist > (outer + aa_band):
                        continue

                    # 0deg at +X, clockwise in widget coordinates (y-down), same as picker math.
                    hue = int(
                        (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0)

                    alpha = 255.0
                    if dist < inner:
                        alpha *= max(0.0, min(1.0,
                                     (dist - (inner - aa_band)) / aa_band))
                    elif dist > outer:
                        alpha *= max(0.0, min(1.0,
                                     ((outer + aa_band) - dist) / aa_band))

                    if alpha <= 0.0:
                        continue

                    c = QColor.fromHsv(hue, 255, 255, int(alpha))
                    wheel_image.setPixelColor(x, y, c)

            self._cached_wheel_image = wheel_image
            self._cached_wheel_size = wheel_size

        painter.drawImage(ring_rect.topLeft(), self._cached_wheel_image)

        sv = self._sv_rect()
        hue_color = self._color_from_hsv(self._hue_255, 255, 255)
        # Cache SV image if size changed or hue changed
        sv_size = (int(sv.width()), int(sv.height()))
        if (
            sv_size != self._cached_sv_size
            or self._cached_sv_image is None
            or self._cached_sv_hue != hue_color.hue()
        ):
            sv_image = QImage(int(sv.width()), int(sv.height()),
                              QImage.Format.Format_ARGB32)
            for y in range(sv_image.height()):
                value = 255 - int((y / max(1, sv_image.height() - 1)) * 255)
                for x in range(sv_image.width()):
                    sat = int((x / max(1, sv_image.width() - 1)) * 255)
                    c = QColor.fromHsv(hue_color.hue(), sat, value)
                    sv_image.setPixelColor(x, y, c)
            self._cached_sv_image = sv_image
            self._cached_sv_size = sv_size
            self._cached_sv_hue = hue_color.hue()

        painter.drawImage(sv.topLeft(), self._cached_sv_image)

        painter.setPen(QPen(QColor(210, 210, 210), 1.0))
        painter.drawRect(sv)

        ring_angle = (self._hue_255 / 255.0) * (2.0 * math.pi)
        r = (inner + outer) * 0.5
        marker_x = center.x() + math.cos(ring_angle) * r
        marker_y = center.y() + math.sin(ring_angle) * r
        painter.setPen(QPen(QColor(15, 15, 15), 2.0))
        painter.setBrush(QColor(225, 225, 225))
        painter.drawEllipse(QPointF(marker_x, marker_y), 5.0, 5.0)

        square_x = sv.left() + (self._sat_255 / 255.0) * sv.width()
        square_y = sv.bottom() - (self._val_255 / 255.0) * sv.height()
        painter.setPen(QPen(QColor(10, 10, 10), 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(square_x, square_y), 5.0, 5.0)
        painter.end()

    def _pick_from_pos(self, pos: QPointF) -> bool:
        center, inner, outer = self._ring_geometry()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        dist2 = dx * dx + dy * dy

        if self._drag_mode == "h":
            angle = math.degrees(math.atan2(dy, dx))
            hue_deg = (angle + 360.0) % 360.0
            old_hue = self._hue_255
            self._hue_255 = _clamp_255(int(round((hue_deg / 359.0) * 255.0)))
            # Invalidate SV cache when hue changes
            if old_hue != self._hue_255:
                self._cached_sv_image = None
            self.update()
            self.color_changed.emit(self._color_from_hsv(
                self._hue_255, self._sat_255, self._val_255))
            return True

        if self._drag_mode == "" and inner * inner <= dist2 <= outer * outer:
            angle = math.degrees(math.atan2(dy, dx))
            hue_deg = (angle + 360.0) % 360.0
            old_hue = self._hue_255
            self._hue_255 = _clamp_255(int(round((hue_deg / 359.0) * 255.0)))
            self._drag_mode = "h"
            # Invalidate SV cache when hue changes
            if old_hue != self._hue_255:
                self._cached_sv_image = None
            self.update()
            self.color_changed.emit(self._color_from_hsv(
                self._hue_255, self._sat_255, self._val_255))
            return True

        sv = self._sv_rect()
        if self._drag_mode == "sv":
            sx = (pos.x() - sv.left()) / max(1.0, sv.width())
            sy = (pos.y() - sv.top()) / max(1.0, sv.height())
            self._sat_255 = _clamp_255(
                int(round(max(0.0, min(1.0, sx)) * 255.0)))
            self._val_255 = _clamp_255(
                int(round((1.0 - max(0.0, min(1.0, sy))) * 255.0)))
            self.update()
            self.color_changed.emit(self._color_from_hsv(
                self._hue_255, self._sat_255, self._val_255))
            return True

        if self._drag_mode == "" and sv.contains(pos):
            self._drag_mode = "sv"
            sx = (pos.x() - sv.left()) / max(1.0, sv.width())
            sy = (pos.y() - sv.top()) / max(1.0, sv.height())
            self._sat_255 = _clamp_255(
                int(round(max(0.0, min(1.0, sx)) * 255.0)))
            self._val_255 = _clamp_255(
                int(round((1.0 - max(0.0, min(1.0, sy))) * 255.0)))
            self.update()
            self.color_changed.emit(self._color_from_hsv(
                self._hue_255, self._sat_255, self._val_255))
            return True
        return False

    # type: ignore[override]
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        if self._pick_from_pos(event.position()):
            if not self._mouse_captured:
                self.grabMouse()
                self._mouse_captured = True
            event.accept()
            return
        event.ignore()

    # type: ignore[override]
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode:
            self._pick_from_pos(event.position())
            event.accept()
            return
        event.ignore()

    # type: ignore[override]
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._mouse_captured:
            self.releaseMouse()
            self._mouse_captured = False
        self._drag_mode = ""
        event.accept()


class _ScreenColorPickOverlay(QWidget):
    """Top-level transparent click-capture for one-shot screen color picking."""

    color_picked = Signal(object)  # QColor
    canceled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        primary = QGuiApplication.primaryScreen()
        geometry = primary.virtualGeometry() if primary is not None else QRect(0, 0, 1, 1)
        self.setGeometry(geometry)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        painter.end()

    def show_and_focus(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    # type: ignore[override]
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.accept()
            return
        color = _sample_screen_pixel(event.globalPosition().toPoint())
        if color is not None:
            self.color_picked.emit(QColor(color))
        self.close()
        event.accept()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.canceled.emit()
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)


class QCompactColorEditorWidget(QWidget):
    """Compact color editor with hue wheel, sliders, and preset swatches."""

    color_changed = Signal(object)  # QColor

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        preset_dir: Path | None = None,
        palette_slots: int = 12,
    ) -> None:
        super().__init__(parent)
        self._preset_dir = preset_dir or (
            _repo_root_from_widget_file() / "data" / "color_swatches")
        self._preset_dir.mkdir(parents=True, exist_ok=True)

        self._color = QColor(245, 198, 229, 255)
        self._mode = "HSVA"
        initial_h, _initial_s, _initial_v, _initial_a = self._color.getHsv()
        if initial_h < 0:
            initial_h = 0
        self._last_hsva_hue_255 = _clamp_255(
            int(round((initial_h / 359.0) * 255.0)))
        self._rows: list[_ColorSliderRow] = []
        self._palette_slots = max(1, int(palette_slots))
        self._palette_sockets: list[_PaletteSocket] = []
        self._window_size_locked = False
        self._screen_pick_overlay: _ScreenColorPickOverlay | None = None

        self._build_ui()
        self._apply_themed_icons()
        self._sync_ui_from_color(emit=False)
        self._refresh_preset_combo()
        # Initialize mode button to show next mode
        self._mode_toggle.setText("RGBA")

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        # If used as a standalone window, size exactly to content and disable resize.
        if self.isWindow() and not self._window_size_locked:
            self.adjustSize()
            self.setFixedSize(self.sizeHint())
            self._window_size_locked = True

    def changeEvent(self, event) -> None:  # type: ignore[override]
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            self._apply_themed_icons()

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self._sync_ui_from_color(emit=True)

    def preset_dir(self) -> Path:
        return self._preset_dir

    def list_preset_names(self) -> list[str]:
        files = sorted(self._preset_dir.glob(f"*{_PRESET_EXTENSION}"))
        return [f.stem for f in files]

    def save_preset_named(self, name: str) -> Path:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Preset name cannot be empty")
        path = self._preset_dir / f"{clean_name}{_PRESET_EXTENSION}"
        payload = {
            "swatches": [
                _color_to_payload(c) if c is not None else None
                for c in [socket.color() for socket in self._palette_sockets]
            ]
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._refresh_preset_combo(select_name=clean_name)
        return path

    def load_preset_file(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        swatches = data.get("swatches", [])
        for index, socket in enumerate(self._palette_sockets):
            color = None
            if index < len(swatches) and isinstance(swatches[index], str):
                color = _payload_to_color(swatches[index])
            socket.set_color(color)
        self._refresh_preset_combo(select_name=path.stem)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        picker_row = QHBoxLayout()
        picker_row.setContentsMargins(0, 0, 0, 0)
        picker_row.setSpacing(6)

        swatch_col = QVBoxLayout()
        swatch_col.setContentsMargins(0, 0, 0, 0)
        swatch_col.setSpacing(3)

        self._current_swatch = _CurrentColorSwatch(self)
        swatch_col.addWidget(self._current_swatch, 0,
                             Qt.AlignmentFlag.AlignLeft)

        self._eyedropper_btn = QToolButton(self)
        self._eyedropper_btn.setToolTip("Pick color from screen")
        self._eyedropper_btn.setAutoRaise(True)
        self._eyedropper_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._eyedropper_btn.setIconSize(QSize(12, 12))
        self._eyedropper_btn.setFixedSize(22, 22)
        self._eyedropper_btn.setText("")
        self._eyedropper_btn.clicked.connect(self._on_eyedropper_clicked)
        swatch_col.addWidget(self._eyedropper_btn, 0,
                             Qt.AlignmentFlag.AlignLeft)
        swatch_col.addStretch(1)
        picker_row.addLayout(swatch_col, 0)

        # Keep picker visually centered by balancing the left swatch with equal right spacing.
        picker_row.addStretch(1)

        self._picker = _HueSatValPicker(self)
        self._picker.color_changed.connect(self._on_picker_color_changed)
        picker_row.addWidget(self._picker, 0, Qt.AlignmentFlag.AlignCenter)
        picker_row.addStretch(1)
        picker_row.addSpacing(self._current_swatch.width())

        root.addLayout(picker_row)

        for label in ("H", "S", "V", "A"):
            row = _ColorSliderRow(label, self)
            row.value_changed.connect(self._on_slider_changed)
            self._rows.append(row)
            root.addWidget(row)
        self._rows[3].set_alpha_style(True)

        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(6)

        # Mode toggle on the left - show what we'll switch TO
        self._mode_toggle = QPushButton("RGBA")
        self._mode_toggle.setCheckable(False)
        self._mode_toggle.setMaximumWidth(48)
        self._mode_toggle.setMaximumHeight(22)
        self._mode_toggle.setFlat(False)
        self._mode_toggle.setStyleSheet(
            "QPushButton { background: rgb(60,60,60); color: rgb(220,220,220); border: 1px solid rgb(80,80,80); padding: 2px; font-size: 10px; margin: 0px; }"
            "QPushButton:hover { background: rgb(80,80,80); }"
            "QPushButton:pressed { background: rgb(40,40,40); }"
        )
        self._mode_toggle.clicked.connect(self._on_toggle_mode)
        preset_row.addWidget(self._mode_toggle, 0)

        preset_row.addWidget(QLabel("Preset", self), 0)

        self._preset_combo = QComboBox(self)
        self._preset_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._preset_combo.currentIndexChanged.connect(
            self._on_preset_combo_changed)
        preset_row.addWidget(self._preset_combo, 1)
        root.addLayout(preset_row)

        swatch_row = QHBoxLayout()
        swatch_row.setContentsMargins(0, 0, 0, 0)
        swatch_row.setSpacing(4)

        strip = QWidget(self)
        strip_grid = QGridLayout(strip)
        strip_grid.setContentsMargins(0, 0, 0, 0)
        strip_grid.setHorizontalSpacing(4)
        strip_grid.setVerticalSpacing(4)

        columns = min(8, self._palette_slots)
        for i in range(self._palette_slots):
            socket = _PaletteSocket(i, strip)
            socket.clicked.connect(self._on_palette_socket_clicked)
            self._palette_sockets.append(socket)
            row = i // columns
            col = i % columns
            strip_grid.addWidget(socket, row, col)
        swatch_row.addWidget(strip, 0)
        swatch_row.addStretch(1)

        self._save_btn = QToolButton(self)
        self._save_btn.setToolTip("Save swatch preset")
        self._save_btn.setAutoRaise(True)
        self._save_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._save_btn.setIconSize(QSize(12, 12))
        self._save_btn.setFixedSize(22, 22)
        self._save_btn.clicked.connect(self._on_save_clicked)
        swatch_row.addWidget(self._save_btn)

        self._load_btn = QToolButton(self)
        self._load_btn.setToolTip("Load swatch preset from file")
        self._load_btn.setAutoRaise(True)
        self._load_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._load_btn.setIconSize(QSize(12, 12))
        self._load_btn.setFixedSize(22, 22)
        self._load_btn.clicked.connect(self._on_load_clicked)
        swatch_row.addWidget(self._load_btn)

        root.addLayout(swatch_row)

    def _refresh_preset_combo(self, select_name: str | None = None) -> None:
        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        names = self.list_preset_names()
        self._preset_combo.addItem("(none)", "")
        for name in names:
            self._preset_combo.addItem(name, name)
        if select_name:
            idx = self._preset_combo.findData(select_name)
            if idx >= 0:
                self._preset_combo.setCurrentIndex(idx)
        self._preset_combo.blockSignals(False)

    def _sync_ui_from_color(self, *, emit: bool) -> None:
        self._current_swatch.set_color(self._color)

        hue_deg, sat, val, alpha = self._color.getHsv()
        if hue_deg >= 0:
            hue_255 = _clamp_255(int(round((hue_deg / 359.0) * 255.0)))
            self._last_hsva_hue_255 = hue_255
        else:
            # Preserve hue when QColor hue is undefined (sat=0, val=0/255, etc.).
            hue_255 = self._last_hsva_hue_255
        hue_deg = int(round((hue_255 / 255.0) * 359.0))
        self._picker.set_hsva(hue_255, sat, val)

        for row in self._rows:
            row.blockSignals(True)

        if self._mode == "HSVA":
            values = [hue_255, sat, val, alpha]
            labels = ["H", "S", "V", "A"]
        else:
            values = [self._color.red(), self._color.green(),
                      self._color.blue(), alpha]
            labels = ["R", "G", "B", "A"]

        for row, label, value in zip(self._rows, labels, values):
            row.set_label(label)
            row.set_value(value)

        # Apply gradient styles to sliders in HSVA mode
        if self._mode == "HSVA":
            self._rows[0].set_hue_style()
            self._rows[1].set_saturation_style(hue=hue_deg, val=val)
            self._rows[2].set_value_style(hue=hue_deg, sat=sat)
            self._rows[3].set_alpha_color_style(self._color)
        else:
            r = self._color.red()
            g = self._color.green()
            b = self._color.blue()
            a = self._color.alpha()
            self._rows[0].set_red_style(g=g, b=b, a=a)
            self._rows[1].set_green_style(r=r, b=b, a=a)
            self._rows[2].set_blue_style(r=r, g=g, a=a)
            self._rows[3].set_alpha_color_style(self._color)

        for row in self._rows:
            row.blockSignals(False)

        if emit:
            self.color_changed.emit(QColor(self._color))

    def _on_picker_color_changed(self, opaque_color: QColor) -> None:
        del opaque_color
        h, s, v = self._picker.hsva()
        hue_deg = int(round((h / 255.0) * 359.0))
        self._color = QColor.fromHsv(hue_deg, s, v, self._color.alpha())
        self._sync_ui_from_color(emit=True)

    def _on_palette_socket_clicked(self, index: int) -> None:
        socket = self._palette_sockets[index]
        color = socket.color()
        if color is None:
            socket.set_color(QColor(self._color))
            return
        self.set_color(color)

    def _on_slider_changed(self, value: int) -> None:
        if self._mode == "HSVA":
            h = self._rows[0].value()
            s = self._rows[1].value()
            v = self._rows[2].value()
            a = self._rows[3].value()
            self._last_hsva_hue_255 = h
            hue_deg = int(round((h / 255.0) * 359.0))
            next_color = QColor.fromHsv(hue_deg, s, v, a)
            self._color = next_color
        else:
            r = self._rows[0].value()
            g = self._rows[1].value()
            b = self._rows[2].value()
            a = self._rows[3].value()
            self._color.setRgb(r, g, b, a)
        self._sync_ui_from_color(emit=True)

    def _on_toggle_mode(self) -> None:
        self._mode = "RGBA" if self._mode == "HSVA" else "HSVA"
        # Show what we'll switch TO next
        next_mode = "HSVA" if self._mode == "RGBA" else "RGBA"
        self._mode_toggle.setText(next_mode)
        self._sync_ui_from_color(emit=False)

    def _on_save_clicked(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Save Swatch Preset", "Preset name:")
        if not ok:
            return
        if not name.strip():
            return
        self.save_preset_named(name.strip())

    def _on_load_clicked(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Swatch Preset",
            str(self._preset_dir),
            "Color Swatch Presets (*.json);;All Files (*)",
        )
        if not file_path:
            return
        self.load_preset_file(Path(file_path))

    def _on_preset_combo_changed(self, index: int) -> None:
        name = self._preset_combo.currentData()
        if not name:
            return
        path = self._preset_dir / f"{name}{_PRESET_EXTENSION}"
        if path.exists():
            self.load_preset_file(path)

    def _apply_themed_icons(self) -> None:
        bg_color = self.palette().color(QPalette.ColorRole.Window)
        icon_color = _icon_color_for_background(bg_color)

        eyedropper_icon = _themed_data_icon(
            "compact_color_eyedropper.svg", icon_color)
        if eyedropper_icon is not None:
            self._eyedropper_btn.setIcon(eyedropper_icon)
        else:
            self._eyedropper_btn.setText("+")

        save_icon = _themed_data_icon("compact_color_save.svg", icon_color)
        if save_icon is not None:
            self._save_btn.setIcon(save_icon)
        else:
            self._save_btn.setIcon(self.style().standardIcon(
                self.style().StandardPixmap.SP_DialogSaveButton))

        load_icon = _themed_data_icon("compact_color_load.svg", icon_color)
        if load_icon is not None:
            self._load_btn.setIcon(load_icon)
        else:
            self._load_btn.setIcon(self.style().standardIcon(
                self.style().StandardPixmap.SP_DialogOpenButton))

    def _on_eyedropper_clicked(self) -> None:
        self._start_screen_pick()

    def _start_screen_pick(self) -> None:
        if self._screen_pick_overlay is not None:
            return
        overlay = _ScreenColorPickOverlay(self.window())
        overlay.color_picked.connect(self._on_screen_color_picked)
        overlay.canceled.connect(self._on_screen_pick_finished)
        overlay.destroyed.connect(self._on_screen_pick_destroyed)
        self._screen_pick_overlay = overlay
        overlay.show_and_focus()

    def _on_screen_color_picked(self, color: QColor) -> None:
        sampled = QColor(color)
        if sampled.isValid():
            picked = QColor(sampled.red(), sampled.green(),
                            sampled.blue(), self._color.alpha())
            self.set_color(picked)
        self._on_screen_pick_finished()

    def _on_screen_pick_finished(self) -> None:
        if self._screen_pick_overlay is None:
            return
        overlay = self._screen_pick_overlay
        self._screen_pick_overlay = None
        overlay.close()
        overlay.deleteLater()

    def _on_screen_pick_destroyed(self, obj: object) -> None:
        del obj
        self._screen_pick_overlay = None


__all__ = ["QCompactColorEditorWidget"]
