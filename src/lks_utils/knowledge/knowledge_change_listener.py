"""Listener protocol for KnowledgeIO change notifications."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from lks_utils.knowledge.knowledge_change_event import KnowledgeChangeEvent


@runtime_checkable
class KnowledgeChangeListener(Protocol):
    """Protocol implemented by change listeners subscribing to KnowledgeIO."""

    def on_knowledge_change(self, event: KnowledgeChangeEvent) -> None:
        """Handle a knowledge change event."""
