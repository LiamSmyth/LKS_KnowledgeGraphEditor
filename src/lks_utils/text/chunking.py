"""Text chunking utilities: split large text into overlapping chunks."""

from __future__ import annotations

# Approximate characters per token (matches TokenCounter.CHARS_PER_TOKEN)
_CHARS_PER_TOKEN: float = 4.0


def chunk_text(
    text: str,
    chunk_size: int = 2000,
    overlap: int = 200,
) -> list[str]:
    """Split text into chunks of approximately ``chunk_size`` tokens with overlap.

    Splitting strategy:
    1. Split by double newlines (paragraphs) first.
    2. If a paragraph still exceeds ``chunk_size``, split by sentences.
    3. Prepend the tail of the previous chunk as overlap context for every
       subsequent chunk so no context is dropped at boundaries.

    Args:
        text: Input text to split.
        chunk_size: Maximum chunk size in approximate tokens (1 token ≈ 4 chars).
        overlap: Number of overlap tokens prepended from the previous chunk.

    Returns:
        List of text chunks in order.  Returns ``[]`` for empty/whitespace input.
    """
    if not text or not text.strip():
        return []

    char_limit: int = max(1, int(chunk_size * _CHARS_PER_TOKEN))
    overlap_chars: int = max(0, int(overlap * _CHARS_PER_TOKEN))

    raw_chunks: list[str] = _build_raw_chunks(text, char_limit)
    if not raw_chunks:
        return []

    if overlap_chars <= 0 or len(raw_chunks) <= 1:
        return raw_chunks

    return _apply_overlap(raw_chunks, overlap_chars)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_raw_chunks(text: str, char_limit: int) -> list[str]:
    """Build chunks without overlap using paragraph-then-sentence splitting."""
    paragraphs: list[str] = text.split("\n\n")
    chunks: list[str] = []
    current_parts: list[str] = []
    current_chars: int = 0

    for para in paragraphs:
        para_chars: int = len(para)

        if para_chars > char_limit:
            # Paragraph too large — split by sentences
            sentences: list[str] = para.replace(". ", ".\n").split("\n")
            for sentence in sentences:
                sent_chars: int = len(sentence)
                if current_chars + sent_chars > char_limit:
                    if current_parts:
                        chunks.append("\n\n".join(current_parts))
                    current_parts = [sentence]
                    current_chars = sent_chars
                else:
                    current_parts.append(sentence)
                    current_chars += sent_chars
        elif current_chars + para_chars > char_limit:
            if current_parts:
                chunks.append("\n\n".join(current_parts))
            current_parts = [para]
            current_chars = para_chars
        else:
            current_parts.append(para)
            current_chars += para_chars

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks


def _apply_overlap(chunks: list[str], overlap_chars: int) -> list[str]:
    """Prepend the tail of the previous chunk as overlap context."""
    result: list[str] = [chunks[0]]
    for i in range(1, len(chunks)):
        prev: str = chunks[i - 1]
        tail: str = prev[-overlap_chars:] if len(
            prev) > overlap_chars else prev
        result.append(tail + "\n\n" + chunks[i])
    return result
