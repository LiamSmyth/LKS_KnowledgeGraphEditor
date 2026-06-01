"""CSV field extraction editor widget.

Qt widget for visually configuring field extraction from CSV rows.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ..base import QDualModeWidget
from ...extraction.csv import CSVFieldExtractor, RowTextFormat
from ...extraction import ExtractionRule
from .composite_rule_builder import QCompositeRuleBuilder


class QCSVFieldExtractionEditor(QDualModeWidget):
    """Widget for configuring CSV field extraction.

    Provides 3 modes:
    - Simple: Column dropdown with fallbacks
    - Constant: Fixed value
    - Advanced: Extraction rules with text format selection

    Signals:
        extraction_changed: Emits (field_name, config_dict) when configuration changes
    """

    extraction_changed = Signal(str, dict)  # (field_name, config_dict)

    def __init__(
        self,
        field_name: str,
        parent: Optional[QWidget] = None,
        state_key: str = "",
    ):
        """Initialize field extraction editor.

        Args:
            field_name: Name of the field being configured
            parent: Parent widget
            state_key: Key for state persistence (QDualModeWidget)
        """
        self.field_name = field_name
        self._available_columns: list[str] = []

        super().__init__(
            parent, state_key=state_key or f"csv_field_editor_{field_name}")

    def _build_main_ui(self, container: QWidget) -> None:
        """Build the main UI content."""
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        # Mode selection
        mode_group = QGroupBox("Extraction Mode")
        mode_layout = QHBoxLayout(mode_group)

        self.simple_radio = QRadioButton("Simple Column")
        self.constant_radio = QRadioButton("Constant Value")
        self.advanced_radio = QRadioButton("Advanced Rule")
        self.simple_radio.setChecked(True)

        mode_layout.addWidget(self.simple_radio)
        mode_layout.addWidget(self.constant_radio)
        mode_layout.addWidget(self.advanced_radio)
        mode_layout.addStretch()

        layout.addWidget(mode_group)

        # Simple mode panel
        self.simple_panel = self._build_simple_panel()
        layout.addWidget(self.simple_panel)

        # Constant mode panel
        self.constant_panel = self._build_constant_panel()
        layout.addWidget(self.constant_panel)

        # Advanced mode panel
        self.advanced_panel = self._build_advanced_panel()
        layout.addWidget(self.advanced_panel)

        # Connect mode switches
        self.simple_radio.toggled.connect(self._on_mode_changed)
        self.constant_radio.toggled.connect(self._on_mode_changed)
        self.advanced_radio.toggled.connect(self._on_mode_changed)

        # Initial visibility
        self._on_mode_changed()

        layout.addStretch()

    def _build_simple_panel(self) -> QWidget:
        """Build simple column extraction panel."""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)

        # Source column
        col_layout = QHBoxLayout()
        col_layout.addWidget(QLabel("Source Column:"))
        self.source_column_combo = QComboBox()
        self.source_column_combo.setEditable(True)
        self.source_column_combo.currentTextChanged.connect(self._emit_change)
        col_layout.addWidget(self.source_column_combo, 1)
        layout.addLayout(col_layout)

        # Fallback columns
        fallback_layout = QHBoxLayout()
        fallback_layout.addWidget(QLabel("Fallback:"))
        self.fallback_edit = QLineEdit()
        self.fallback_edit.setPlaceholderText("Column2, Column3 (optional)")
        self.fallback_edit.textChanged.connect(self._emit_change)
        fallback_layout.addWidget(self.fallback_edit, 1)
        layout.addLayout(fallback_layout)

        # Default value
        default_layout = QHBoxLayout()
        default_layout.addWidget(QLabel("Default:"))
        self.default_value_edit = QLineEdit()
        self.default_value_edit.setPlaceholderText("Value if column empty")
        self.default_value_edit.textChanged.connect(self._emit_change)
        default_layout.addWidget(self.default_value_edit, 1)
        layout.addLayout(default_layout)

        return panel

    def _build_constant_panel(self) -> QWidget:
        """Build constant value panel."""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)

        const_layout = QHBoxLayout()
        const_layout.addWidget(QLabel("Constant Value:"))
        self.constant_value_edit = QLineEdit()
        self.constant_value_edit.textChanged.connect(self._emit_change)
        const_layout.addWidget(self.constant_value_edit, 1)
        layout.addLayout(const_layout)

        return panel

    def _build_advanced_panel(self) -> QWidget:
        """Build advanced extraction rule panel."""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)

        # Text format selection
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Row Format:"))
        self.text_format_combo = QComboBox()
        self.text_format_combo.addItems(
            ["json", "key_value", "csv_line", "columns"])
        self.text_format_combo.currentTextChanged.connect(self._emit_change)
        format_layout.addWidget(self.text_format_combo)
        format_layout.addStretch()
        layout.addLayout(format_layout)

        # Rule builder
        self.rule_builder = QCompositeRuleBuilder()
        self.rule_builder.rule_changed.connect(self._emit_change)
        layout.addWidget(self.rule_builder, 1)

        return panel

    def _on_mode_changed(self) -> None:
        """Handle mode radio button changes."""
        self.simple_panel.setVisible(self.simple_radio.isChecked())
        self.constant_panel.setVisible(self.constant_radio.isChecked())
        self.advanced_panel.setVisible(self.advanced_radio.isChecked())
        self._emit_change()

    def _emit_change(self) -> None:
        """Emit extraction_changed signal with current config."""
        config = self.get_config()
        self.extraction_changed.emit(self.field_name, config)

    def update_available_columns(self, columns: list[str]) -> None:
        """Update available columns for dropdown.

        Args:
            columns: List of column names from CSV
        """
        self._available_columns = columns

        current = self.source_column_combo.currentText()
        self.source_column_combo.clear()
        self.source_column_combo.addItems(columns)

        if current in columns:
            self.source_column_combo.setCurrentText(current)

    def get_config(self) -> Dict[str, Any]:
        """Get current extraction configuration.

        Returns:
            Dictionary suitable for CSVFieldExtractor.from_dict()
        """
        config: Dict[str, Any] = {
            "field_name": self.field_name,
        }

        if self.simple_radio.isChecked():
            # Simple column mode
            source_col = self.source_column_combo.currentText().strip()
            if source_col:
                config["source_column"] = source_col

            fallback_text = self.fallback_edit.text().strip()
            if fallback_text:
                fallbacks = [c.strip()
                             for c in fallback_text.split(",") if c.strip()]
                if fallbacks:
                    config["fallback_columns"] = fallbacks

            default_val = self.default_value_edit.text().strip()
            if default_val:
                config["default_value"] = default_val

        elif self.constant_radio.isChecked():
            # Constant value mode
            const_val = self.constant_value_edit.text().strip()
            if const_val:
                config["constant_value"] = const_val

        elif self.advanced_radio.isChecked():
            # Advanced rule mode
            rule = self.rule_builder.get_rule()
            if rule:
                config["extraction_rule"] = rule.to_dict()

            config["text_format"] = self.text_format_combo.currentText()

        return config

    def set_config(self, config: Dict[str, Any]) -> None:
        """Load extraction configuration.

        Args:
            config: Configuration from CSVFieldExtractor.to_dict()
        """
        # Determine mode
        if "constant_value" in config:
            self.constant_radio.setChecked(True)
            self.constant_value_edit.setText(config["constant_value"])

        elif "extraction_rule" in config:
            self.advanced_radio.setChecked(True)
            rule = ExtractionRule.from_dict(config["extraction_rule"])
            self.rule_builder.set_rule(rule)

            text_format = config.get("text_format", "json")
            idx = self.text_format_combo.findText(text_format)
            if idx >= 0:
                self.text_format_combo.setCurrentIndex(idx)

        else:
            # Simple mode
            self.simple_radio.setChecked(True)

            source_col = config.get("source_column", "")
            if source_col:
                self.source_column_combo.setCurrentText(source_col)

            fallbacks = config.get("fallback_columns", [])
            if fallbacks:
                self.fallback_edit.setText(", ".join(fallbacks))

            default_val = config.get("default_value", "")
            if default_val:
                self.default_value_edit.setText(default_val)

    def get_extractor(self) -> CSVFieldExtractor:
        """Create CSVFieldExtractor from current configuration.

        Returns:
            Configured field extractor
        """
        config = self.get_config()
        return CSVFieldExtractor.from_dict(config)
