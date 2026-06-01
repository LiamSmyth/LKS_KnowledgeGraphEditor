"""Helper utilities shared by knowledge workbench creation dialogs."""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox

from lks_utils.knowledge.models.node import Node
from lks_utils.knowledge.models.type import as_type


def populate_category_combo(
    combo: QComboBox,
    type_nodes: list[Node],
    *,
    include_empty_option: bool = False,
) -> None:
    """Populate *combo* with existing instance-category values from *type_nodes*."""
    seen: set[str] = set()
    combo.clear()
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    if include_empty_option:
        combo.addItem("(No Category)", "")
        combo.setCurrentIndex(0)

    for type_node in type_nodes:
        type_view = as_type(type_node)
        if not type_view.category or type_view.category in seen:
            continue
        seen.add(type_view.category)
        combo.addItem(
            f"{type_node.name} ({type_view.category})", type_view.category)


def combo_value(combo: QComboBox) -> str:
    """Return the current editable/user-entered value for a combo box."""
    current_text = combo.currentText().strip()
    current_index = combo.currentIndex()
    if combo.isEditable() and current_text:
        if current_index < 0 or current_text != combo.itemText(current_index):
            return current_text
    current_data = combo.currentData()
    if isinstance(current_data, str):
        return current_data.strip()
    return current_text


__all__ = ["populate_category_combo", "combo_value"]
