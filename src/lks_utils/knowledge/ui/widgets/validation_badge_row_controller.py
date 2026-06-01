"""Controller that binds validation index changes to row badges."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from lks_utils.gui_qt.widgets.q_validation_badge import QValidationBadge
    from lks_utils.knowledge.validation_index import ValidationIndex


class ValidationBadgeRowController(QObject):
    """Update row badges from ValidationIndex with selective per-id refresh."""

    def __init__(
        self,
        validation_index: ValidationIndex,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._validation_index = validation_index
        self._badges_by_object_id: dict[str,
                                        list[QValidationBadge]] = defaultdict(list)
        self._validation_index.validation_changed.connect(
            self._on_validation_changed)

    def attach_row(
        self,
        object_id: str,
        row_widget: QWidget,
        badge: QValidationBadge,
    ) -> None:
        """Attach one row badge and apply current status immediately."""
        _ = row_widget
        self._badges_by_object_id[object_id].append(badge)
        badge.set_status(self._validation_index.status_for(object_id))

    def detach_row(self, object_id: str) -> None:
        """Detach all row badges associated with one object id."""
        self._badges_by_object_id.pop(object_id, None)

    def _on_validation_changed(self, changed_ids: object) -> None:
        if not isinstance(changed_ids, (set, frozenset, list, tuple)):
            return

        for object_id in self._normalize_ids(changed_ids):
            badges = self._badges_by_object_id.get(object_id)
            if not badges:
                continue
            status = self._validation_index.status_for(object_id)
            for badge in badges:
                badge.set_status(status)

    @staticmethod
    def _normalize_ids(changed_ids: Iterable[object]) -> set[str]:
        normalized: set[str] = set()
        for object_id in changed_ids:
            normalized.add(str(object_id))
        return normalized


__all__ = ["ValidationBadgeRowController"]
