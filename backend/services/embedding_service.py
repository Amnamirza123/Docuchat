"""
Embedding wrapper using Google's Gemini embedding model
(gemini-embedding-001), truncated to 768 dimensions to match the
vector(768) column in Supabase.

Retry + pacing: Google's free tier rate-limits embedding requests per
minute. Long documents (novels, large PDFs) can generate hundreds of
chunks, which without pacing hits that limit mid-upload and crashes
the whole document. embed_batch retries on failure with backoff and
adds a small delay between calls to stay under the limit.
"""

import time
import google.generativeai as genai
from config import settings

genai.configure(api_key=settings.google_api_key)

MAX_RETRIES = 4
BASE_DELAY_SECONDS = 2
PACING_DELAY_SECONDS = 0.3  # small gap between calls to avoid bursting the rate limit


def _embed_with_retry(text: str, task_type: str) -> list[float]:
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            result = genai.embed_content(
                model=settings.embedding_model,
                content=text,
                task_type=task_type,
                output_dimensionality=768,
            )
            return result["embedding"]
        except Exception as e:
            last_error = e
            wait = BASE_DELAY_SECONDS * (2 ** attempt)
            print(f"[DEBUG] embed attempt {attempt + 1} failed: {e} — retrying in {wait}s")
            time.sleep(wait)
    raise last_error


def embed_text(text: str) -> list[float]:
    """Embeds a single string (used for the user's query at chat time)."""
    return _embed_with_retry(text, "retrieval_query")


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embeds many chunks, one at a time with pacing + retry, so long
    documents don't crash the whole upload on a single rate-limit hit."""
    if not texts:
        return []

    embeddings = []
    for i, text in enumerate(texts):
        embeddings.append(_embed_with_retry(text, "retrieval_document"))
        if i < len(texts) - 1:
            time.sleep(PACING_DELAY_SECONDS)
    return embeddings