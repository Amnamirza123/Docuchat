"""
Chunking strategy: recursive splitting on paragraph/sentence boundaries,
token-aware sizing via tiktoken, with overlap to preserve context across
chunk edges. Each chunk keeps its source page number for citations.

Full rationale lives in docs/chunking_writeup.md — short version: fixed-size
character chunking cuts sentences mid-thought and hurts retrieval precision,
while pure semantic/LLM-based chunking is slow and hard to validate in a
week-long eval cycle. Recursive splitting is the standard middle ground.
"""

import tiktoken
from config import settings
from services.document_service import ParsedPage

encoding = tiktoken.get_encoding("cl100k_base")


class Chunk:
    def __init__(self, content: str, page_number: int, chunk_index: int):
        self.content = content
        self.page_number = page_number
        self.chunk_index = chunk_index


def _token_len(text: str) -> int:
    return len(encoding.encode(text))


def _split_into_sentences(text: str) -> list[str]:
    # Lightweight sentence split — good enough for chunking purposes,
    # avoids pulling in a heavier NLP dependency.
    import re
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in sentences if s]


def _chunk_page_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Greedily fills chunks with whole sentences up to chunk_size tokens,
    then backs up `overlap` tokens worth of trailing sentences to start
    the next chunk — so no chunk ever cuts a sentence in half.
    """
    sentences = _split_into_sentences(text)
    if not sentences:
        return []

    chunks = []
    current_sentences: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = _token_len(sentence)

        if current_tokens + sentence_tokens > chunk_size and current_sentences:
            chunks.append(" ".join(current_sentences))

            # Build overlap: keep trailing sentences until we hit `overlap` tokens
            overlap_sentences = []
            overlap_tokens = 0
            for s in reversed(current_sentences):
                t = _token_len(s)
                if overlap_tokens + t > overlap:
                    break
                overlap_sentences.insert(0, s)
                overlap_tokens += t

            current_sentences = overlap_sentences
            current_tokens = overlap_tokens

        current_sentences.append(sentence)
        current_tokens += sentence_tokens

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return chunks


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