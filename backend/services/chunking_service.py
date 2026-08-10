"""
Chunking strategy: recursive splitting on sentence boundaries, token-aware
sizing via tiktoken, with overlap to preserve context across chunk edges.
Each chunk keeps its source page number for citations.

NEW — document-structure-aware chunking: as text is scanned, heading-like
lines (e.g. "Week 3: RAG Systems...", "Day 3: Supabase & pgvector") are
detected and tracked as a running "heading trail." Every chunk gets its
current heading trail prepended to its content before embedding.

Why this matters: sentence-boundary chunking alone has no idea that a
bullet like "Day 3: Supabase & pgvector" belongs under a "Week 3:" heading
several lines above it. If they land in different chunks (likely in a
long structured document), the "Day 3" chunk's embedding has no "Week 3"
context in it at all — so a query mentioning "week 3" won't match it well,
even though the answer is genuinely there. Prepending the active heading
trail keeps that parent context attached to every chunk under it,
regardless of where sentence/token boundaries fall.
"""

import re
import tiktoken
from config import settings
from services.document_service import ParsedPage

encoding = tiktoken.get_encoding("cl100k_base")

# Matches lines like "Week 3: RAG Systems", "Day 3: Supabase & pgvector",
# "Chapter 2 -", "Section 4.1", etc. — short lines starting with a
# heading-like keyword followed by a number, optionally with a colon/dash.
HEADING_PATTERN = re.compile(
    r"^\s*(week|day|chapter|section|part|module|unit|step)\s*\d+\s*[:\-.]?",
    re.IGNORECASE,
)
MAX_HEADING_LINE_LENGTH = 100  # headings are short; a 300-char sentence starting with "Day 3" isn't one


class Chunk:
    def __init__(self, content: str, page_number: int, chunk_index: int):
        self.content = content
        self.page_number = page_number
        self.chunk_index = chunk_index


def _token_len(text: str) -> int:
    return len(encoding.encode(text))


def _is_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > MAX_HEADING_LINE_LENGTH:
        return False
    return bool(HEADING_PATTERN.match(line))


def _heading_level(line: str) -> str:
    """Returns the heading keyword (week/day/chapter/...) in lowercase,
    used to decide whether a new heading replaces or nests under the
    current trail — e.g. a new 'Week' resets 'Day', but a new 'Day'
    under the same 'Week' just updates the day slot."""
    match = HEADING_PATTERN.match(line.strip())
    return match.group(1).lower() if match else ""


def _split_into_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in sentences if s]


def _extract_headings_and_body(page_text: str) -> list[tuple[str, str]]:
    """
    Splits page text into lines, tags each line as heading or body, and
    returns a list of (heading_trail_at_this_point, line_text) so the
    chunker can track which headings are active as it scans through.
    Trail order is broad-to-narrow, e.g. "Week 3 > Day 3".
    """
    lines = page_text.split("\n")
    trail: dict[str, str] = {}  # e.g. {"week": "Week 3: RAG Systems", "day": "Day 3: Supabase & pgvector"}
    tagged_lines = []

    # Priority order: broader structural terms reset narrower ones.
    RESET_ORDER = ["part", "chapter", "module", "unit", "week", "section", "day", "step"]

    for line in lines:
        if _is_heading(line):
            level = _heading_level(line)
            trail[level] = line.strip()
            # Clear any narrower headings that come after this one in RESET_ORDER,
            # since a new "Week" heading means the old "Day" no longer applies.
            if level in RESET_ORDER:
                idx = RESET_ORDER.index(level)
                for narrower in RESET_ORDER[idx + 1:]:
                    trail.pop(narrower, None)

        current_trail = " > ".join(
            trail[k] for k in RESET_ORDER if k in trail
        )
        tagged_lines.append((current_trail, line))

    return tagged_lines


def _chunk_page_text(page_text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Greedily fills chunks with whole sentences up to chunk_size tokens,
    carries overlap into the next chunk, and prepends the active heading
    trail (if any) to each chunk's content.
    """
    tagged_lines = _extract_headings_and_body(page_text)

    # Re-join into (heading_trail, sentence) pairs so trail info survives
    # sentence splitting, not just line splitting.
    sentence_entries: list[tuple[str, str]] = []
    for trail, line in tagged_lines:
        for sentence in _split_into_sentences(line):
            sentence_entries.append((trail, sentence))

    if not sentence_entries:
        return []

    chunks = []
    current_entries: list[tuple[str, str]] = []
    current_tokens = 0

    for trail, sentence in sentence_entries:
        sentence_tokens = _token_len(sentence)

        if current_tokens + sentence_tokens > chunk_size and current_entries:
            chunks.append(_finalize_chunk(current_entries))

            overlap_entries = []
            overlap_tokens = 0
            for t, s in reversed(current_entries):
                tok = _token_len(s)
                if overlap_tokens + tok > overlap:
                    break
                overlap_entries.insert(0, (t, s))
                overlap_tokens += tok

            current_entries = overlap_entries
            current_tokens = overlap_tokens

        current_entries.append((trail, sentence))
        current_tokens += sentence_tokens

    if current_entries:
        chunks.append(_finalize_chunk(current_entries))

    return chunks


def _finalize_chunk(entries: list[tuple[str, str]]) -> str:
    """Prepends the most specific (last-seen) heading trail in this chunk
    to its text content, so the embedding includes that context."""
    body = " ".join(s for _, s in entries)
    trails = [t for t, _ in entries if t]
    heading_prefix = trails[-1] if trails else ""
    if heading_prefix:
        return f"[{heading_prefix}] {body}"
    return body


def chunk_document(pages: list[ParsedPage]) -> list[Chunk]:
    chunk_size = settings.chunk_size_tokens
    overlap = settings.chunk_overlap_tokens

    all_chunks: list[Chunk] = []
    global_index = 0

    for page in pages:
        page_chunks = _chunk_page_text(page.text, chunk_size, overlap)
        for text in page_chunks:
            all_chunks.append(
                Chunk(content=text, page_number=page.page_number, chunk_index=global_index)
            )
            global_index += 1

    return all_chunks