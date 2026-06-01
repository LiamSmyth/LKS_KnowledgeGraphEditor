"""State machine contract for graph link-creation modal workflow."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GraphLinkCreationState(str, Enum):
    """Modal states for drag-driven ad-hoc graph link creation."""

    IDLE = "idle"
    SOURCE_SELECT = "source_select"
    TARGET_SELECT = "target_select"


class GraphLinkCreationEvent(str, Enum):
    """Logical events consumed by the link-creation transition table."""

    BEGIN = "begin"
    SOURCE_CONFIRM = "source_confirm"
    TARGET_COMMIT = "target_commit"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class GraphLinkCreationTransitionResult:
    """Result of one transition-table evaluation."""

    next_state: GraphLinkCreationState
    committed: bool = False
    cancelled: bool = False


def transition_graph_link_creation_state(
    state: GraphLinkCreationState,
    event: GraphLinkCreationEvent,
    *,
    valid_hit: bool = True,
) -> GraphLinkCreationTransitionResult:
    """Evaluate one modal-state transition.

    The transition contract matches the feature design notes:
    - ``Idle`` + ``Begin`` -> ``SourceSelect``
    - ``SourceSelect`` + valid ``SourceConfirm`` -> ``TargetSelect``
    - ``SourceSelect`` + invalid ``SourceConfirm`` -> cancel to ``Idle``
    - ``TargetSelect`` + valid ``TargetCommit`` -> commit to ``Idle``
    - ``TargetSelect`` + invalid ``TargetCommit`` -> cancel to ``Idle``
    - ``Cancel`` from any modal state -> cancel to ``Idle``
    """
    if event == GraphLinkCreationEvent.BEGIN:
        if state != GraphLinkCreationState.IDLE:
            return GraphLinkCreationTransitionResult(next_state=state)
        return GraphLinkCreationTransitionResult(
            next_state=GraphLinkCreationState.SOURCE_SELECT
        )

    if event == GraphLinkCreationEvent.CANCEL:
        if state == GraphLinkCreationState.IDLE:
            return GraphLinkCreationTransitionResult(next_state=state)
        return GraphLinkCreationTransitionResult(
            next_state=GraphLinkCreationState.IDLE,
            cancelled=True,
        )

    if event == GraphLinkCreationEvent.SOURCE_CONFIRM:
        if state != GraphLinkCreationState.SOURCE_SELECT:
            return GraphLinkCreationTransitionResult(next_state=state)
        if valid_hit:
            return GraphLinkCreationTransitionResult(
                next_state=GraphLinkCreationState.TARGET_SELECT
            )
        return GraphLinkCreationTransitionResult(
            next_state=GraphLinkCreationState.IDLE,
            cancelled=True,
        )

    if event == GraphLinkCreationEvent.TARGET_COMMIT:
        if state != GraphLinkCreationState.TARGET_SELECT:
            return GraphLinkCreationTransitionResult(next_state=state)
        if valid_hit:
            return GraphLinkCreationTransitionResult(
                next_state=GraphLinkCreationState.IDLE,
                committed=True,
            )
        return GraphLinkCreationTransitionResult(
            next_state=GraphLinkCreationState.IDLE,
            cancelled=True,
        )

    return GraphLinkCreationTransitionResult(next_state=state)


__all__ = [
    "GraphLinkCreationEvent",
    "GraphLinkCreationState",
    "GraphLinkCreationTransitionResult",
    "transition_graph_link_creation_state",
]
