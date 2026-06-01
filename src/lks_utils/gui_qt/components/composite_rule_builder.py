"""Composite rule builder component for chaining extraction rules."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.map_editor import QMapEditorComponent
from lks_utils.gui_qt.components.row_filter import QRowFilterComponent
from lks_utils.gui_qt.theme import COLORS
from lks_utils.gui_qt.widgets import QGripBoxContainer, QGripBoxItem
from lks_utils.extraction import (
    CompositeExtractionRule,
    DelimiterExtractRule,
    JsonArrayExtractRule,
    JsonObjectExtractRule,
    LineSelectRule,
    PrefixExtractRule,
    RegexExtractRule,
    SplitExtractRule,
    SubstringMapRule,
    ColumnSelectRule,
    ColumnMapRule,
    RowFilterRule as ExtractionRowFilterRule,
)
from lks_utils.extraction.extraction_rules.text_rules.delimiter_extract_rule_ui import (
    DelimiterExtractRuleUI,
)
from lks_utils.extraction.extraction_rules.text_rules.json_array_extract_rule_ui import (
    JsonArrayExtractRuleUI,
)
from lks_utils.extraction.extraction_rules.text_rules.json_object_extract_rule_ui import (
    JsonObjectExtractRuleUI,
)
from lks_utils.extraction.extraction_rules.text_rules.line_select_rule_ui import (
    LineSelectRuleUI,
)
from lks_utils.extraction.extraction_rules.text_rules.prefix_extract_rule_ui import (
    PrefixExtractRuleUI,
)
from lks_utils.extraction.extraction_rules.text_rules.regex_extract_rule_ui import (
    RegexExtractRuleUI,
)
from lks_utils.extraction.extraction_rules.text_rules.split_extract_rule_ui import (
    SplitExtractRuleUI,
)


class QCompositeRuleBuilder(QWidget):
    """Component for building composite extraction rules.

    Allows user to:
    - Add/remove/reorder rule steps
    - Configure each step's rule type and parameters
    - Preview intermediate results for each step
    - Drag-to-reorder steps

    Each step is one of:
    - RegexExtractRule
    - SubstringMapRule
    - SplitExtractRule
    - LineSelectRule
    - DelimiterExtractRule
    - PrefixExtractRule
    - JsonObjectExtractRule
    - JsonArrayExtractRule
    - ColumnSelectRule
    - ColumnMapRule
    - RowFilterRule

    Signals:
    - rule_changed: Emitted when rule configuration changes
    """

    rule_changed = Signal(dict)  # {rules: list[dict]}

    # Supported rule types with display names
    RULE_TYPES = [
        ("regex", "Regex Extract"),
        ("substring_map", "Substring Map"),
        ("split", "Split Extract"),
        ("line_select", "Line Select"),
        ("delimiter", "Delimiter Extract"),
        ("prefix", "Prefix Extract"),
        ("json_object", "JSON Object Extract"),
        ("json_array", "JSON Array Extract"),
        ("column_select", "Column Select"),
        ("column_map", "Column Map"),
        ("row_filter", "Row Filter"),
    ]

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize composite rule builder.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # State
        self._steps: list[dict[str, Any]] = []
        self._sample_input = ""

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the component UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # --- Sample Input ---
        input_label = QLabel("Sample Input (for preview):")
        input_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(input_label)

        self._sample_input_edit = QTextEdit()
        self._sample_input_edit.setPlaceholderText(
            "Paste sample text here to see how rules transform it...")
        self._sample_input_edit.setMaximumHeight(100)
        self._sample_input_edit.textChanged.connect(self._on_sample_changed)
        layout.addWidget(self._sample_input_edit)

        # --- Rule Steps List ---
        steps_label = QLabel("Rule Steps (drag to reorder):")
        steps_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(steps_label)

        self._steps_container = QGripBoxContainer()
        self._steps_container.setMinimumHeight(200)
        self._steps_container.order_changed.connect(self._on_order_changed)
        layout.addWidget(self._steps_container)

        # --- Step Buttons ---
        button_layout = QHBoxLayout()

        self._add_btn = QPushButton("Add Step")
        self._add_btn.clicked.connect(self._add_step)
        button_layout.addWidget(self._add_btn)

        self._edit_btn = QPushButton("Edit Step")
        self._edit_btn.clicked.connect(self._edit_selected_step)
        button_layout.addWidget(self._edit_btn)

        self._remove_btn = QPushButton("Remove Step")
        self._remove_btn.clicked.connect(self._remove_step)
        button_layout.addWidget(self._remove_btn)

        self._preview_btn = QPushButton("Preview Pipeline")
        self._preview_btn.clicked.connect(self._show_preview)
        button_layout.addWidget(self._preview_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # --- Info Label ---
        self._info_label = QLabel("0 steps")
        self._info_label.setStyleSheet(
            f"color: {COLORS['light']}; font-size: 10px;")
        layout.addWidget(self._info_label)

    def _on_sample_changed(self) -> None:
        """Handle sample input change."""
        self._sample_input = self._sample_input_edit.toPlainText()

    def _on_order_changed(self) -> None:
        """Handle steps reordered via drag-drop."""
        # Rebuild steps list from current container order
        new_steps = []
        for i in range(self._steps_container.count()):
            item = self._steps_container.item_at(i)
            if item and hasattr(item, 'property') and item.property('step_index') is not None:
                step_index = item.property('step_index')
                if 0 <= step_index < len(self._steps):
                    new_steps.append(self._steps[step_index])

        self._steps = new_steps
        self._refresh_list()
        self._emit_change()

    def _refresh_list(self) -> None:
        """Refresh the steps list display."""
        self._steps_container.clear()

        for idx, step in enumerate(self._steps):
            rule_type = step.get("type", "unknown")
            rule_name = next(
                (name for rt, name in self.RULE_TYPES if rt == rule_type), "Unknown")

            # Build display text with step number and brief config
            display_text = f"{idx + 1}. {rule_name}"

            # Add brief config summary based on rule type
            if rule_type == "regex":
                pattern = step.get("pattern", "")
                display_text += f" — /{pattern[:30]}.../" if len(
                    pattern) > 30 else f" — /{pattern}/"
            elif rule_type == "substring_map":
                mappings = step.get("mappings", {})
                display_text += f" — {len(mappings)} mappings"
            elif rule_type == "split":
                delimiter = step.get("delimiter", "")
                index = step.get("index", 0)
                display_text += f" — split by '{delimiter}', index {index}"
            elif rule_type == "column_select":
                column = step.get("column", "")
                display_text += f" — column '{column}'"
            elif rule_type == "column_map":
                column = step.get("column", "")
                mappings = step.get("mappings", {})
                display_text += f" — column '{column}', {len(mappings)} mappings"
            elif rule_type == "row_filter":
                column = step.get("column", "")
                operator = step.get("operator", "")
                display_text += f" — {column} {operator}"

            # Create label widget for this step
            step_label = QLabel(display_text)
            step_label.setStyleSheet("padding: 8px; background: #2d2d2d;")
            step_label.mouseDoubleClickEvent = lambda e, i=idx: self._edit_step_by_index(
                i)

            # Wrap in grip box item
            grip_item = QGripBoxItem(step_label)
            grip_item.setProperty('step_index', idx)
            self._steps_container.add_item(grip_item)

        # Update info label
        count = len(self._steps)
        self._info_label.setText(f"{count} step{'s' if count != 1 else ''}")

    def _add_step(self) -> None:
        """Open dialog to add a new step."""
        dialog = _RuleStepEditorDialog(parent=self, step=None)

        if dialog.exec() == QDialog.Accepted:
            step_config = dialog.get_config()
            self._steps.append(step_config)
            self._refresh_list()
            self._emit_change()

    def _edit_selected_step(self) -> None:
        """Edit the selected step."""
        # Just edit the first step if none selected
        if len(self._steps) > 0:
            self._edit_step_by_index(0)
        else:
            QMessageBox.information(
                self, "No Steps", "No steps to edit. Add a step first.")

    def _edit_step_by_index(self, step_index: int) -> None:
        """Edit a step by its index."""
        if step_index < 0 or step_index >= len(self._steps):
            return

        step = self._steps[step_index]

        dialog = _RuleStepEditorDialog(parent=self, step=step)

        if dialog.exec() == QDialog.Accepted:
            self._steps[step_index] = dialog.get_config()
            self._refresh_list()
            self._emit_change()

    def _remove_step(self) -> None:
        """Remove the last step."""
        if not self._steps:
            QMessageBox.information(
                self, "No Steps", "No steps to remove.")
            return

        step_index = len(self._steps) - 1

        # Confirm removal
        reply = QMessageBox.question(
            self,
            "Remove Step",
            f"Remove step {step_index + 1}?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self._steps.pop(step_index)
            self._refresh_list()
            self._emit_change()

    def _show_preview(self) -> None:
        """Show preview of pipeline execution with intermediate results."""
        if not self._steps:
            QMessageBox.information(
                self, "No Steps", "Add at least one rule step to preview.")
            return

        if not self._sample_input:
            QMessageBox.information(
                self, "No Sample Input", "Enter sample input text to preview.")
            return

        # Build and execute the rule pipeline
        try:
            rules = self._build_extraction_rules()
            composite = CompositeExtractionRule(rules)
            test_result = composite.test(self._sample_input)

            # Build preview text with intermediate results
            preview_text = "Pipeline Preview:\n\n"
            preview_text += f"Input:\n{self._sample_input}\n\n"
            preview_text += "=" * 60 + "\n\n"

            for idx, step in enumerate(self._steps):
                rule_type = step.get("type", "unknown")
                rule_name = next(
                    (name for rt, name in self.RULE_TYPES if rt == rule_type), "Unknown")
                preview_text += f"Step {idx + 1}: {rule_name}\n"
                preview_text += f"  Config: {step}\n"

                if idx < len(test_result.intermediate_steps):
                    output = test_result.intermediate_steps[idx]
                    preview_text += f"  Output: {output}\n"
                else:
                    preview_text += "  Output: (no output)\n"
                preview_text += "\n"

            preview_text += "=" * 60 + "\n\n"
            preview_text += f"Final Result:\n"
            if test_result.matched:
                preview_text += f"✓ Success: {test_result.extracted_value}\n"
            else:
                preview_text += f"✗ Failed: {test_result.error_message or 'No match'}\n"

        except Exception as e:
            preview_text = f"Error executing pipeline:\n\n{str(e)}"

        # Show in dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Pipeline Preview")
        dialog.resize(800, 600)

        layout = QVBoxLayout(dialog)

        preview_edit = QTextEdit()
        preview_edit.setReadOnly(True)
        preview_edit.setPlainText(preview_text)
        layout.addWidget(preview_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)

        dialog.exec()

    def _build_extraction_rules(self) -> list:
        """Build ExtractionRule objects from step configs.

        Returns:
            List of ExtractionRule instances

        Raises:
            ValueError: If a step config is invalid
        """
        rules = []

        for step in self._steps:
            rule_type = step.get("type")

            if rule_type == "regex":
                pattern = step.get("pattern", "")
                group = step.get("group", 0)
                rules.append(RegexExtractRule(pattern=pattern, group=group))

            elif rule_type == "substring_map":
                mapping = step.get("mapping", {})
                rules.append(SubstringMapRule(mapping=mapping))

            elif rule_type == "split":
                delimiter = step.get("delimiter", ",")
                index = step.get("index", 0)
                rules.append(SplitExtractRule(
                    delimiter=delimiter, index=index))

            elif rule_type == "line_select":
                line_index = step.get("line_index", 0)
                rules.append(LineSelectRule(index=line_index))

            elif rule_type == "delimiter":
                start = step.get("start_delimiter", "")
                end = step.get("end_delimiter", "")
                rules.append(DelimiterExtractRule(start=start, end=end))

            elif rule_type == "prefix":
                prefix = step.get("prefix", "")
                rules.append(PrefixExtractRule(prefix=prefix))

            elif rule_type == "json_object":
                key_path = step.get("key_path", "")
                rules.append(JsonObjectExtractRule(key_path=key_path))

            elif rule_type == "json_array":
                index = step.get("index", 0)
                rules.append(JsonArrayExtractRule(index=index))

            elif rule_type == "column_select":
                column = step.get("column", 0)
                has_header = step.get("has_header", False)
                rules.append(ColumnSelectRule(
                    column=column, has_header=has_header))

            elif rule_type == "column_map":
                mapping = step.get("mapping", {})
                rules.append(ColumnMapRule(mapping=mapping))

            elif rule_type == "row_filter":
                filters = step.get("filters", [])
                rules.append(ExtractionRowFilterRule(filters=filters))

            else:
                raise ValueError(f"Unknown rule type: {rule_type}")

        return rules

        dialog.exec()

    def _emit_change(self) -> None:
        """Emit rule changed signal."""
        config = self.get_config()
        self.rule_changed.emit(config)

    # --- Public API ---

    def get_config(self) -> dict[str, Any]:
        """Get current rule configuration.

        Returns:
            Dictionary with key 'rules': list of rule configs
        """
        return {
            "rules": [step.copy() for step in self._steps],
        }

    def set_config(self, config: dict[str, Any]) -> None:
        """Set rule configuration.

        Args:
            config: Dictionary with key 'rules': list of rule configs
        """
        if "rules" in config:
            self._steps = [step.copy() for step in config["rules"]]
            self._refresh_list()
            self._emit_change()

    def get_rules(self) -> list[dict[str, Any]]:
        """Get list of rules.

        Returns:
            List of rule config dicts
        """
        return [step.copy() for step in self._steps]

    def set_rules(self, rules: list[dict[str, Any]]) -> None:
        """Set list of rules.

        Args:
            rules: List of rule config dicts
        """
        self._steps = [rule.copy() for rule in rules]
        self._refresh_list()
        self._emit_change()

    def to_dict(self) -> dict:
        """Export component state to dictionary.

        Returns:
            State dictionary
        """
        return {
            "rules": self.get_rules(),
            "sample_input": self._sample_input,
        }

    def from_dict(self, state: dict) -> None:
        """Load component state from dictionary.

        Args:
            state: State dictionary
        """
        if "rules" in state:
            self.set_rules(state["rules"])
        if "sample_input" in state:
            self._sample_input_edit.setPlainText(state["sample_input"])


class _RuleStepEditorDialog(QDialog):
    """Dialog for editing a single rule step."""

    def __init__(
        self,
        parent: QWidget | None = None,
        step: dict[str, Any] | None = None,
    ) -> None:
        """Initialize rule step editor dialog.

        Args:
            parent: Parent widget
            step: Existing step config to edit (None for new step)
        """
        super().__init__(parent)

        self.setWindowTitle("Edit Rule Step" if step else "Add Rule Step")
        self.resize(600, 400)

        self._step_config = step.copy() if step else {}

        self._build_ui()

        # Load existing config if editing
        if step:
            self._load_config(step)

    def _build_ui(self) -> None:
        """Build the dialog UI."""
        layout = QVBoxLayout(self)

        # Rule type selector
        type_layout = QHBoxLayout()

        type_label = QLabel("Rule Type:")
        type_layout.addWidget(type_label)

        self._type_combo = QComboBox()
        for rule_id, rule_name in QCompositeRuleBuilder.RULE_TYPES:
            self._type_combo.addItem(rule_name, rule_id)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_layout.addWidget(self._type_combo, stretch=1)

        layout.addLayout(type_layout)

        # Dynamic config area
        self._config_widget = QWidget()
        self._config_layout = QVBoxLayout(self._config_widget)
        self._config_layout.setContentsMargins(0, 10, 0, 10)
        layout.addWidget(self._config_widget)

        # Info label
        self._info_label = QLabel(
            "Configure the rule parameters above. "
            "Complex rules will open separate editor dialogs."
        )
        self._info_label.setStyleSheet(
            f"color: {COLORS['light']}; font-size: 10px;")
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Trigger initial UI build
        self._on_type_changed()

    def _clear_layout(self, layout: QLayout) -> None:
        """Recursively clear all items from a layout.

        Args:
            layout: Layout to clear
        """
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                widget = child.widget()
                widget.setParent(None)
                widget.deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())

    def _on_type_changed(self) -> None:
        """Handle rule type selection change."""
        # Clear existing config widgets
        while self._config_layout.count():
            child = self._config_layout.takeAt(0)
            if child.widget():
                widget = child.widget()
                widget.setParent(None)
                widget.deleteLater()
            elif child.layout():
                # Recursively clear nested layouts
                self._clear_layout(child.layout())

        rule_type = self._type_combo.currentData()

        # Create type-specific config UI using dedicated UI classes
        self._current_rule_ui = None

        if rule_type == "regex":
            self._current_rule_ui = RegexExtractRuleUI()
        elif rule_type == "split":
            self._current_rule_ui = SplitExtractRuleUI()
        elif rule_type == "line_select":
            self._current_rule_ui = LineSelectRuleUI()
        elif rule_type == "delimiter":
            self._current_rule_ui = DelimiterExtractRuleUI()
        elif rule_type == "prefix":
            self._current_rule_ui = PrefixExtractRuleUI()
        elif rule_type == "json_object":
            self._current_rule_ui = JsonObjectExtractRuleUI()
        elif rule_type == "json_array":
            self._current_rule_ui = JsonArrayExtractRuleUI()
        elif rule_type == "substring_map":
            # Placeholder - will integrate map editor
            info = QLabel("Substring map configuration coming soon...")
            info.setWordWrap(True)
            self._config_layout.addWidget(info)
        elif rule_type == "column_select":
            # Placeholder - will create UI class
            info = QLabel("Column select configuration coming soon...")
            info.setWordWrap(True)
            self._config_layout.addWidget(info)
        elif rule_type == "column_map":
            # Placeholder - will integrate map editor
            info = QLabel("Column map configuration coming soon...")
            info.setWordWrap(True)
            self._config_layout.addWidget(info)
        elif rule_type == "row_filter":
            # Placeholder - will integrate row filter component
            info = QLabel("Row filter configuration coming soon...")
            info.setWordWrap(True)
            self._config_layout.addWidget(info)

        if self._current_rule_ui:
            self._config_layout.addWidget(self._current_rule_ui)

    def _build_regex_config(self) -> None:
        """Build config UI for regex extract rule."""
        # Help text
        help_label = QLabel(
            "<b>Regex Extract:</b> Uses regular expressions to extract text.<br>"
            "<b>Example:</b> Pattern <code>Error: (\\d+)</code> on text \"Error: 404\" → extracts \"404\"<br>"
            "Use parentheses () to create capture groups."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;")
        self._config_layout.addWidget(help_label)

        label = QLabel("Pattern:")
        label.setToolTip(
            "Regular expression pattern. Use () for capture groups.")
        self._config_layout.addWidget(label)

        self._regex_pattern_edit = QLineEdit()
        self._regex_pattern_edit.setPlaceholderText(
            r"Enter regex pattern, e.g., (\d+)")
        self._regex_pattern_edit.setToolTip(
            "Example patterns:\n"
            r"  (\d+) - captures one or more digits" "\n"
            r"  ([A-Z]{3}) - captures 3 uppercase letters" "\n"
            r"  ERROR: (.*) - captures everything after 'ERROR: '"
        )
        self._config_layout.addWidget(self._regex_pattern_edit)

        group_layout = QHBoxLayout()
        group_label = QLabel("Capture Group:")
        group_label.setToolTip("0 = full match, 1+ = capture groups in ()")
        group_layout.addWidget(group_label)

        self._regex_group_combo = QComboBox()
        self._regex_group_combo.addItem("0 (full match)", 0)
        for i in range(1, 10):
            self._regex_group_combo.addItem(f"Group {i}", i)
        self._regex_group_combo.setToolTip(
            "Which part to extract:\n"
            "  0 = entire match\n"
            "  1 = first () group\n"
            "  2 = second () group, etc."
        )
        group_layout.addWidget(self._regex_group_combo)
        group_layout.addStretch()

        self._config_layout.addLayout(group_layout)

    def _build_substring_map_config(self) -> None:
        """Build config UI for substring map rule."""
        info_label = QLabel(
            "Click 'OK' to open the map editor in a separate window.\n"
            "(Map editor integration pending)"
        )
        info_label.setWordWrap(True)
        self._config_layout.addWidget(info_label)

    def _build_split_config(self) -> None:
        """Build config UI for split extract rule."""
        # Help text
        help_label = QLabel(
            "<b>Split Extract:</b> Splits text by delimiter and extracts one element.<br>"
            "<b>Example:</b> Delimiter <code>,</code> index <code>1</code> on \"apple,banana,cherry\" → extracts \"banana\""
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;")
        self._config_layout.addWidget(help_label)

        delim_layout = QHBoxLayout()
        delim_label = QLabel("Delimiter:")
        delim_label.setToolTip(
            "Character(s) to split on (e.g., comma, space, pipe)")
        delim_layout.addWidget(delim_label)

        self._split_delimiter_edit = QLineEdit()
        self._split_delimiter_edit.setPlaceholderText(",")
        self._split_delimiter_edit.setToolTip(
            "Examples: ',' or '|' or ' - ' or '\\t' (tab)")
        delim_layout.addWidget(self._split_delimiter_edit)

        self._config_layout.addLayout(delim_layout)

        index_layout = QHBoxLayout()
        index_label = QLabel("Element Index:")
        index_label.setToolTip(
            "Which piece to extract (0 = first, 1 = second, -1 = last)")
        index_layout.addWidget(index_label)

        self._split_index_edit = QLineEdit()
        self._split_index_edit.setPlaceholderText("0")
        self._split_index_edit.setToolTip(
            "0-based index. Use negative numbers to count from end.")
        index_layout.addWidget(self._split_index_edit)

        self._config_layout.addLayout(index_layout)

    def _build_line_select_config(self) -> None:
        """Build config UI for line select rule."""
        # Help text
        help_label = QLabel(
            "<b>Line Select:</b> Extracts a specific line from multi-line text.<br>"
            "<b>Example:</b> Index <code>1</code> on \"line1\\nline2\\nline3\" → extracts \"line2\""
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;")
        self._config_layout.addWidget(help_label)

        line_layout = QHBoxLayout()
        line_label = QLabel("Line Index:")
        line_label.setToolTip("Which line to extract (0 = first, -1 = last)")
        line_layout.addWidget(line_label)

        self._line_index_edit = QLineEdit()
        self._line_index_edit.setPlaceholderText(
            "0 (or negative for from end)")
        self._line_index_edit.setToolTip(
            "0-based index:\n"
            "  0 = first line\n"
            "  1 = second line\n"
            "  -1 = last line\n"
            "  -2 = second to last"
        )
        line_layout.addWidget(self._line_index_edit)

        self._config_layout.addLayout(line_layout)

    def _build_delimiter_config(self) -> None:
        """Build config UI for delimiter extract rule."""
        # Help text
        help_label = QLabel(
            "<b>Delimiter Extract:</b> Extracts text between two delimiters.<br>"
            "<b>Example:</b> Start <code>[</code> End <code>]</code> on \"Error: [404] Not Found\" → extracts \"404\""
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;")
        self._config_layout.addWidget(help_label)

        start_layout = QHBoxLayout()
        start_label = QLabel("Start Delimiter:")
        start_label.setToolTip("Text that marks the beginning of extraction")
        start_layout.addWidget(start_label)

        self._delim_start_edit = QLineEdit()
        self._delim_start_edit.setPlaceholderText("e.g., [")
        self._delim_start_edit.setToolTip(
            "Examples: '[' or 'START:' or '(' or '<'")
        start_layout.addWidget(self._delim_start_edit)

        self._config_layout.addLayout(start_layout)

        end_layout = QHBoxLayout()
        end_label = QLabel("End Delimiter:")
        end_label.setToolTip("Text that marks the end of extraction")
        end_layout.addWidget(end_label)

        self._delim_end_edit = QLineEdit()
        self._delim_end_edit.setPlaceholderText("e.g., ]")
        self._delim_end_edit.setToolTip("Examples: ']' or 'END' or ')' or '>'")
        end_layout.addWidget(self._delim_end_edit)

        self._config_layout.addLayout(end_layout)

    def _build_prefix_config(self) -> None:
        """Build config UI for prefix extract rule."""
        # Help text
        help_label = QLabel(
            "<b>Prefix Extract:</b> Finds line starting with prefix and extracts the rest.<br>"
            "<b>Example:</b> Prefix <code>Result: </code> on multi-line text with \"Result: SUCCESS\" → extracts \"SUCCESS\""
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;")
        self._config_layout.addWidget(help_label)

        prefix_layout = QHBoxLayout()
        prefix_label = QLabel("Line Prefix:")
        prefix_label.setToolTip(
            "Text that appears at the start of the line to extract")
        prefix_layout.addWidget(prefix_label)

        self._prefix_edit = QLineEdit()
        self._prefix_edit.setPlaceholderText("e.g., 'Result: '")
        self._prefix_edit.setToolTip(
            "Examples:\n"
            "  'Error: ' - finds line starting with 'Error: '\n"
            "  'ID=' - finds line starting with 'ID='\n"
            "  '> ' - finds line starting with '> '"
        )
        prefix_layout.addWidget(self._prefix_edit)

        self._config_layout.addLayout(prefix_layout)

    def _build_json_object_config(self) -> None:
        """Build config UI for JSON object extract rule."""
        # Help text
        help_label = QLabel(
            "<b>JSON Object Extract:</b> Finds and extracts the first JSON object.<br>"
            "<b>Example:</b> Text \"Response: {\"status\": \"ok\", \"code\": 200}\" → extracts the JSON object<br>"
            "Can then be chained with other rules to extract specific keys."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;")
        self._config_layout.addWidget(help_label)

        info_label = QLabel(
            "Automatically detects and extracts JSON objects from text.\n"
            "No configuration needed - just extracts first {} object found."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"color: {COLORS['light']};")
        self._config_layout.addWidget(info_label)

    def _build_json_array_config(self) -> None:
        """Build config UI for JSON array extract rule."""
        # Help text
        help_label = QLabel(
            "<b>JSON Array Extract:</b> Finds and extracts the first JSON array.<br>"
            "<b>Example:</b> Text \"Items: [\"apple\", \"banana\", \"cherry\"]\" → extracts the array<br>"
            "Can be chained with other rules to extract specific elements."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;")
        self._config_layout.addWidget(help_label)

        info_label = QLabel(
            "Automatically detects and extracts JSON arrays from text.\n"
            "No configuration needed - just extracts first [] array found."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"color: {COLORS['light']};")
        self._config_layout.addWidget(info_label)

    def _build_column_select_config(self) -> None:
        """Build config UI for column select rule."""
        # Help text
        help_label = QLabel(
            "<b>Column Select:</b> Extracts a specific column from CSV/TSV data.<br>"
            "<b>Example:</b> Column <code>1</code> on \"apple,banana,cherry\" → extracts \"banana\"<br>"
            "Can use column name if data has headers."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;")
        self._config_layout.addWidget(help_label)

        col_layout = QHBoxLayout()
        col_label = QLabel("Column:")
        col_label.setToolTip("Column name (if headers exist) or 0-based index")
        col_layout.addWidget(col_label)

        self._column_edit = QLineEdit()
        self._column_edit.setPlaceholderText(
            "Column name or index (0, 1, 2...)")
        self._column_edit.setToolTip(
            "Examples:\n"
            "  0 - first column\n"
            "  1 - second column\n"
            "  'name' - column named 'name'"
        )
        col_layout.addWidget(self._column_edit)

        self._config_layout.addLayout(col_layout)

    def _build_column_map_config(self) -> None:
        """Build config UI for column map rule."""
        col_layout = QHBoxLayout()
        col_label = QLabel("Column:")
        col_layout.addWidget(col_label)

        self._column_map_column_edit = QLineEdit()
        self._column_map_column_edit.setPlaceholderText("Column name or index")
        col_layout.addWidget(self._column_map_column_edit)

        self._config_layout.addLayout(col_layout)

        info_label = QLabel(
            "Click 'OK' to open the map editor in a separate window.\n"
            "(Map editor integration pending)"
        )
        info_label.setWordWrap(True)
        self._config_layout.addWidget(info_label)

    def _build_row_filter_config(self) -> None:
        """Build config UI for row filter rule."""
        info_label = QLabel(
            "Click 'OK' to open the filter editor in a separate window.\n"
            "(Filter editor integration pending)"
        )
        info_label.setWordWrap(True)
        self._config_layout.addWidget(info_label)

    def _load_config(self, config: dict[str, Any]) -> None:
        """Load existing config into UI."""
        rule_type = config.get("type", "")

        # Set rule type combo (this triggers _on_type_changed which creates the UI)
        index = self._type_combo.findData(rule_type)
        if index >= 0:
            self._type_combo.setCurrentIndex(index)

        # Load config into the rule UI if it exists
        if hasattr(self, '_current_rule_ui') and self._current_rule_ui:
            self._current_rule_ui.set_config(config)

    def _on_accept(self) -> None:
        """Handle OK button click."""
        rule_type = self._type_combo.currentData()

        # Validate if we have a rule UI
        if hasattr(self, '_current_rule_ui') and self._current_rule_ui:
            is_valid, error_msg = self._current_rule_ui.validate()
            if not is_valid:
                QMessageBox.warning(self, "Validation Error", error_msg)
                return

            # Get config from the UI
            config = {"type": rule_type}
            config.update(self._current_rule_ui.get_config())
        else:
            # Placeholder types without UI yet
            config = {"type": rule_type}

        self._step_config = config
        self.accept()
        # TODO: open filter editor dialog

        self._step_config = config
        self.accept()

    def get_config(self) -> dict[str, Any]:
        """Get the configured step.

        Returns:
            Step configuration dictionary
        """
        return self._step_config.copy()


__all__ = ["QCompositeRuleBuilder"]
