"""Central blast-radius policy for KnowledgeIO mutations."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from lks_utils.knowledge.io.mutation_effects import MutationKind
from lks_utils.knowledge.io.operation_result import ValidationMode


class CanvasHygieneHint(str, Enum):
    """Projection hygiene actions suggested to the controller layer."""

    NONE = "none"
    CACHED_NAME_REFRESH = "cached_name_refresh"
    REMOVE_PLACEMENTS = "remove_placements"
    REMOVE_KB_EDGE = "remove_kb_edge"
    SYNC_KB_EDGE = "sync_kb_edge"


@dataclass(frozen=True)
class PolicyResult:
    """Resolved validation, integrity, and projection hints for one mutate."""

    validation_mode: ValidationMode
    run_integrity_scan: bool
    referencer_expansion: bool
    canvas_hygiene_hint: CanvasHygieneHint


def resolve_policy(
    kind: MutationKind,
    structural_delta: bool,
) -> PolicyResult:
    """Map mutation kind + structural delta to blast-radius policy."""
    if kind is MutationKind.INSTANCE_PROPERTY:
        return PolicyResult(
            validation_mode=ValidationMode.TOUCHED,
            run_integrity_scan=False,
            referencer_expansion=False,
            canvas_hygiene_hint=CanvasHygieneHint.NONE,
        )

    if kind is MutationKind.INSTANCE_PROPERTY_REF:
        return PolicyResult(
            validation_mode=ValidationMode.EXPANDED,
            run_integrity_scan=False,
            referencer_expansion=True,
            canvas_hygiene_hint=CanvasHygieneHint.NONE,
        )

    if kind is MutationKind.NODE_UPSERT:
        return PolicyResult(
            validation_mode=ValidationMode.TOUCHED,
            run_integrity_scan=structural_delta,
            referencer_expansion=False,
            canvas_hygiene_hint=CanvasHygieneHint.CACHED_NAME_REFRESH,
        )

    if kind is MutationKind.NODE_DELETE:
        return PolicyResult(
            validation_mode=ValidationMode.EXPANDED,
            run_integrity_scan=True,
            referencer_expansion=True,
            canvas_hygiene_hint=CanvasHygieneHint.REMOVE_PLACEMENTS,
        )

    if kind is MutationKind.LINK_STRUCTURE:
        hygiene = (
            CanvasHygieneHint.REMOVE_KB_EDGE
            if structural_delta
            else CanvasHygieneHint.NONE
        )
        return PolicyResult(
            validation_mode=ValidationMode.EXPANDED,
            run_integrity_scan=True,
            referencer_expansion=True,
            canvas_hygiene_hint=hygiene,
        )

    if kind is MutationKind.TYPE_SCHEMA:
        return PolicyResult(
            validation_mode=ValidationMode.EXPANDED,
            run_integrity_scan=True,
            referencer_expansion=True,
            canvas_hygiene_hint=CanvasHygieneHint.NONE,
        )

    # GRAPH_VIEW and unknown kinds — conservative defaults for KB path.
    return PolicyResult(
        validation_mode=ValidationMode.TOUCHED,
        run_integrity_scan=False,
        referencer_expansion=False,
        canvas_hygiene_hint=CanvasHygieneHint.NONE,
    )


__all__ = [
    "CanvasHygieneHint",
    "PolicyResult",
    "resolve_policy",
]
