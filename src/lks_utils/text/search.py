"""Small text-search helpers for case-insensitive matching and suggestions."""
from __future__ import annotations

from difflib import get_close_matches


def normalize_search_text(value: str) -> str:
    """Return a trimmed, case-insensitive token for human text lookup."""
    return value.strip().casefold()


def suggest_close_matches(
    query: str,
    candidates: list[str],
    *,
    max_results: int = 3,
    cutoff: float = 0.6,
) -> list[str]:
    """Return close human-facing suggestions for *query* from *candidates*."""
    normalized_query = normalize_search_text(query)
    if not normalized_query:
        return []

    normalized_to_display: dict[str, str] = {}
    normalized_candidates: list[str] = []
    for candidate in candidates:
        normalized = normalize_search_text(candidate)
        if not normalized or normalized in normalized_to_display:
            continue
        normalized_to_display[normalized] = candidate.strip()
        normalized_candidates.append(normalized)

    matches = get_close_matches(
        normalized_query,
        normalized_candidates,
        n=max_results,
        cutoff=cutoff,
    )
    return [normalized_to_display[match] for match in matches]
