"""Row filter component for CSV/table filtering."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.theme import COLORS


class QRowFilterComponent(QWidget):
    """Component for building row filter expressions.

    Allows user to configure:
    - Column name/index
    - Operator (equals, contains, starts_with, ends_with, not_equals, etc.)
    - Value(s) to match

    Used for filtering CSV rows in the RowFilterRule.

    Signals:
    - filter_changed: Emitted when filter configuration changes
    """

    filter_changed = Signal(dict)  # {column, operator, value, case_sensitive}

    # Supported operators
    OPERATORS = [
        ("equals", "Equals"),
        ("not_equals", "Not Equals"),
        ("contains", "Contains"),
        ("not_contains", "Does Not Contain"),
        ("starts_with", "Starts With"),
        ("ends_with", "Ends With"),
        ("matches_regex", "Matches Regex"),
        ("is_empty", "Is Empty"),
        ("is_not_empty", "Is Not Empty"),
        ("greater_than", "Greater Than (>)"),
        ("greater_equal", "Greater or Equal (>=)"),
        ("less_than", "Less Than (<)"),
        ("less_equal", "Less or Equal (<=)"),
        ("in_list", "In List (comma-separated)"),
        ("not_in_list", "Not In List"),
    ]

    def __init__(
        self,
        parent: QWidget | None = None,
        allow_column_index: bool = True,
    ) -> None:
        """Initialize row filter component.

        Args:
            parent: Parent widget
            allow_column_index: Whether to allow column index (numeric) as well as name
        """
        super().__init__(parent)

        self._allow_column_index = allow_column_index

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the component UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # --- Column Selection ---
        column_layout = QHBoxLayout()
        column_layout.setSpacing(5)

        column_label = QLabel("Column:")
        column_layout.addWidget(column_label)

        self._column_entry = QLineEdit()
        self._column_entry.setPlaceholderText(
            "Column name or index (0, 1, 2...)" if self._allow_column_index else "Column name"
        )
        self._column_entry.textChanged.connect(self._emit_change)
        column_layout.addWidget(self._column_entry, stretch=1)

        layout.addLayout(column_layout)

        # --- Operator Selection ---
        operator_layout = QHBoxLayout()
        operator_layout.setSpacing(5)

        operator_label = QLabel("Operator:")
        operator_layout.addWidget(operator_label)

        self._operator_combo = QComboBox()
        for op_id, op_label in self.OPERATORS:
            self._operator_combo.addItem(op_label, op_id)
        self._operator_combo.currentIndexChanged.connect(
            self._on_operator_changed)
        operator_layout.addWidget(self._operator_combo, stretch=1)

        layout.addLayout(operator_layout)

        # --- Value Entry ---
        value_layout = QHBoxLayout()
        value_layout.setSpacing(5)

        self._value_label = QLabel("Value:")
        value_layout.addWidget(self._value_label)

        self._value_entry = QLineEdit()
        self._value_entry.setPlaceholderText("Enter value...")
        self._value_entry.textChanged.connect(self._emit_change)
        value_layout.addWidget(self._value_entry, stretch=1)

        layout.addLayout(value_layout)

        # --- Options ---
        options_layout = QHBoxLayout()
        options_layout.setSpacing(10)

        self._case_sensitive_btn = QPushButton("Case Sensitive: OFF")
        self._case_sensitive_btn.setCheckable(True)
        self._case_sensitive_btn.setChecked(False)
        self._case_sensitive_btn.clicked.connect(self._toggle_case_sensitive)
        options_layout.addWidget(self._case_sensitive_btn)

        self._invert_btn = QPushButton("Invert Match: OFF")
        self._invert_btn.setCheckable(True)
        self._invert_btn.setChecked(False)
        self._invert_btn.clicked.connect(self._toggle_invert)
        options_layout.addWidget(self._invert_btn)

        options_layout.addStretch()

        layout.addLayout(options_layout)

        # Update initial state
        self._on_operator_changed()

    def _on_operator_changed(self) -> None:
        """Handle operator selection change."""
        operator = self._operator_combo.currentData()

        # Hide value field for operators that don't need it
        value_not_needed = operator in ["is_empty", "is_not_empty"]
        self._value_label.setVisible(not value_not_needed)
        self._value_entry.setVisible(not value_not_needed)

        # Update placeholder based on operator
        if operator == "in_list" or operator == "not_in_list":
            self._value_entry.setPlaceholderText("value1, value2, value3...")
        elif operator == "matches_regex":
            self._value_entry.setPlaceholderText(
                "Regular expression pattern...")
        elif operator in ["greater_than", "greater_equal", "less_than", "less_equal"]:
            self._value_entry.setPlaceholderText("Numeric value...")
        else:
            self._value_entry.setPlaceholderText("Enter value...")

        self._emit_change()

    def _toggle_case_sensitive(self) -> None:
        """Toggle case sensitivity."""
        is_on = self._case_sensitive_btn.isChecked()
        self._case_sensitive_btn.setText(
            f"Case Sensitive: {'ON' if is_on else 'OFF'}"
        )
        self._emit_change()

    def _toggle_invert(self) -> None:
        """Toggle invert match."""
        is_on = self._invert_btn.isChecked()
        self._invert_btn.setText(f"Invert Match: {'ON' if is_on else 'OFF'}")
        self._emit_change()

    def _emit_change(self) -> None:
        """Emit filter changed signal."""
        config = self.get_config()
        self.filter_changed.emit(config)

    # --- Public API ---

    def get_config(self) -> dict[str, Any]:
        """Get current filter configuration.

        Returns:
            Dictionary with keys:
            - column: str - column name or index
            - operator: str - operator ID
            - value: str - filter value (empty for is_empty/is_not_empty)
            - case_sensitive: bool
            - invert: bool
        """
        column = self._column_entry.text().strip()
        operator = self._operator_combo.currentData()
        value = self._value_entry.text().strip()
        case_sensitive = self._case_sensitive_btn.isChecked()
        invert = self._invert_btn.isChecked()

        return {
            "column": column,
            "operator": operator,
            "value": value,
            "case_sensitive": case_sensitive,
            "invert": invert,
        }

    def set_config(self, config: dict[str, Any]) -> None:
        """Set filter configuration.

        Args:
            config: Dictionary with keys: column, operator, value, case_sensitive, invert
        """
        # Block signals during batch update
        self.blockSignals(True)

        if "column" in config:
            self._column_entry.setText(config["column"])

        if "operator" in config:
            operator = config["operator"]
            index = self._operator_combo.findData(operator)
            if index >= 0:
                self._operator_combo.setCurrentIndex(index)

        if "value" in config:
            self._value_entry.setText(config["value"])

        if "case_sensitive" in config:
            self._case_sensitive_btn.setChecked(config["case_sensitive"])
            self._toggle_case_sensitive()

        if "invert" in config:
            self._invert_btn.setChecked(config["invert"])
            self._toggle_invert()

        self.blockSignals(False)

        # Update UI based on operator
        self._on_operator_changed()

        # Emit change
        self._emit_change()

    def validate(self) -> tuple[bool, str]:
        """Validate current configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        column = self._column_entry.text().strip()
        if not column:
            return False, "Column name or index is required"

        operator = self._operator_combo.currentData()
        value = self._value_entry.text().strip()

        # Check if value is needed for this operator
        value_not_needed = operator in ["is_empty", "is_not_empty"]
        if not value_not_needed and not value:
            return False, "Value is required for this operator"

        # For numeric operators, check if value is numeric
        if operator in ["greater_than", "greater_equal", "less_than", "less_equal"]:
            try:
                float(value)
            except ValueError:
                return False, "Value must be numeric for comparison operators"

        return True, ""

    def to_dict(self) -> dict:
        """Export component state to dictionary.

        Returns:
            State dictionary
        """
        return self.get_config()

    def from_dict(self, state: dict) -> None:
        """Load component state from dictionary.

        Args:
            state: State dictionary
        """
        self.set_config(state)


__all__ = ["QRowFilterComponent"]
