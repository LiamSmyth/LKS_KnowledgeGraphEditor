"""QExtensionSection — per-registered-extension collapsible editor panel."""
from __future__ import annotations

import dataclasses

from lks_utils.theme.color import Color
from lks_utils.theme.theme_extension import ThemeExtension
from lks_utils.gui_qt.theme_editor.color_swatch_widget import QColorSwatchWidget

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QLineEdit,
    QCheckBox,
    QSizePolicy,
)
from PySide6.QtCore import Signal


class QExtensionSection(QWidget):
    """Displays one collapsible ``QGroupBox`` per ``ThemeExtension``.

    Each field dispatches on its type:
    - ``Color``  → ``QColorSwatchWidget``
    - ``int``    → ``QSpinBox``
    - ``str``    → ``QLineEdit``
    - ``bool``   → ``QCheckBox``

    Emits ``extensions_changed(dict[str, ThemeExtension])`` whenever any
    field is edited.
    """

    extensions_changed = Signal(object)  # dict[str, ThemeExtension]

    def __init__(
        self,
        extensions: dict[str, ThemeExtension] | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._extensions: dict[str, ThemeExtension] = dict(extensions or {})
        # _widgets[module_key][field_name] = editor widget
        self._widgets: dict[str, dict[str, QWidget]] = {}

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(4)

        self._placeholder = QLabel("No theme extensions registered.")
        self._placeholder.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        self._root.addWidget(self._placeholder)
        self._root.addStretch(1)

        self._rebuild(self._extensions)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_extensions(self, extensions: dict[str, ThemeExtension]) -> None:
        """Reload all panels from *extensions* (full replace)."""
        self._extensions = dict(extensions)
        self._rebuild(self._extensions)

    def extensions(self) -> dict[str, ThemeExtension]:
        """Return the currently edited extensions dict."""
        return dict(self._extensions)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild(self, extensions: dict[str, ThemeExtension]) -> None:
        """Tear down old panels and build fresh ones from *extensions*."""
        # Remove old group boxes (keep placeholder + stretch)
        for key in list(self._widgets):
            pass  # groups are owned by _root; remove via iteration below

        # Remove all widgets except nothing (we clear and re-add)
        while self._root.count():
            item = self._root.takeAt(0)
            if item.widget():
                item.widget().setParent(None)  # type: ignore[arg-type]

        self._widgets.clear()

        if not extensions:
            self._root.addWidget(self._placeholder)
            self._placeholder.show()
            self._root.addStretch(1)
            return

        self._placeholder.hide()

        for module_key, ext in sorted(extensions.items()):
            group = QGroupBox(module_key)
            form = QFormLayout(group)
            form.setContentsMargins(8, 8, 8, 8)
            form.setSpacing(6)

            field_editors: dict[str, QWidget] = {}

            for field_name, value in sorted(ext.fields.items()):
                editor = self._make_editor(field_name, value)
                form.addRow(field_name, editor)
                field_editors[field_name] = editor

            self._widgets[module_key] = field_editors
            self._root.addWidget(group)

        self._root.addStretch(1)

    def _make_editor(self, field_name: str, value: object) -> QWidget:
        """Create and wire an editor widget for *value*."""
        if isinstance(value, Color):
            # Pass empty label — the QFormLayout row already shows the field name
            w = QColorSwatchWidget("", value)
            w.color_changed.connect(
                lambda c, fn=field_name: self._on_field_changed(fn, c)
            )
            return w

        if isinstance(value, bool):
            w = QCheckBox()
            w.setChecked(value)
            w.toggled.connect(
                lambda v, fn=field_name: self._on_field_changed(fn, bool(v))
            )
            return w

        if isinstance(value, int):
            w = QSpinBox()
            w.setRange(-2 ** 30, 2 ** 30)
            w.setValue(value)
            w.valueChanged.connect(
                lambda v, fn=field_name: self._on_field_changed(fn, int(v))
            )
            return w

        if isinstance(value, str):
            w = QLineEdit(value)
            w.textEdited.connect(
                lambda v, fn=field_name: self._on_field_changed(fn, v)
            )
            return w

        # Fallback — read-only label
        return QLabel(str(value))

    def _on_field_changed(self, field_name: str, new_value: object) -> None:
        """Update the in-memory extension containing *field_name* and emit."""
        # Find which module_key owns this field_name
        for module_key, field_widgets in self._widgets.items():
            if field_name in field_widgets:
                ext = self._extensions[module_key]
                updated_fields = {**ext.fields, field_name: new_value}
                self._extensions[module_key] = dataclasses.replace(
                    ext, fields=updated_fields
                )
                self.extensions_changed.emit(dict(self._extensions))
                return


__all__ = ["QExtensionSection"]
