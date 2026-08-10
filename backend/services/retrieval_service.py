"""
Session-scoped similarity search + the groundedness threshold decision.

Threshold rule: if the TOP retrieved chunk's similarity score is higher
than the AVERAGE score across all retrieved chunks, the answer is treated
as grounded. Otherwise, there's no clear winner among the retrieved
chunks, so we don't force a document-based answer.
"""

from supabase_client import supabase_admin
from services.embedding_service import embed_text
from config import settings
from models import RetrievedChunk

def retrieve_chunks(query: str, chat_session_id: str) -> list[RetrievedChunk]:
    query_embedding = embed_text(query)

    print(f"[DEBUG] Retrieving for session {chat_session_id}")

    result = supabase_admin.rpc(
        "match_chunks",
        {
            "query_embedding": query_embedding,
            "session_id": chat_session_id,
            "match_count": settings.retrieval_top_k,
        },
    ).execute()
    for row in result.data:
        print(f"[DEBUG] chunk doc_id={row['document_id']} similarity={row['similarity']:.3f}")

    
    return [
        RetrievedChunk(
            id=row["id"],
            document_id=row["document_id"],
            content=row["content"],
            page_number=row.get("page_number"),
            chunk_index=row["chunk_index"],
            similarity=row["similarity"],
        )
        for row in result.data
    ]


def is_grounded(chunks: list[RetrievedChunk]) -> tuple[bool, float]:
    """
    Returns (is_grounded, top_score).
    Grounded when the top chunk's score beats the average of all
    retrieved chunks' scores — a self-calibrating threshold rather
    than a fixed cutoff.
    """
    if not chunks:
        return False, 0.0

    scores = [c.similarity for c in chunks]
    avg_score = sum(scores) / len(scores)
    top_score = scores[0]  # match_chunks already orders by similarity desc

    return top_score > avg_score, top_score


def get_grounding_context(query: str, chat_session_id: str) -> tuple[bool, float, list[RetrievedChunk]]:
    """
    Single entry point rag_service.py calls: retrieves chunks for a
    session, then decides grounded vs. not. Returns everything needed
    downstream — grounded flag, score, and the chunks to cite.
    """
    chunks = retrieve_chunks(query, chat_session_id)
    grounded, top_score = is_grounded(chunks)

    if not grounded:
        return False, 0.0, []

    return True, top_score, chunks
"""
Session-scoped similarity search + the groundedness threshold decision,
with a lightweight CRAG-style (Corrective RAG) correction step.

Threshold rule: grounded when EITHER
  (a) the top chunk's score beats the average score across all
      retrieved chunks (the original self-calibrating rule), OR
  (b) the top chunk's absolute score clears a minimum bar (0.45)
      even if it doesn't beat the average.

Correction step (CRAG-inspired): if the first retrieval is borderline
(neither clearly grounded nor clearly empty — the top score falls in a
"weak but not nothing" band), the query is reformulated by the LLM into
better search terms and retrieval is retried once before giving up.
This targets exactly the failure mode where a user's phrasing ("day 3
week 3") doesn't closely match the document's actual phrasing ("Week 3
... Day 3: Supabase & pgvector"), which a single fixed-threshold pass
would reject even though the answer is genuinely present.
"""

from openai import OpenAI

from supabase_client import supabase_admin
from services.embedding_service import embed_text
from config import settings
from models import RetrievedChunk

MIN_ABSOLUTE_SCORE = 0.45
WEAK_BAND_FLOOR = 0.30  # below this, don't even bother retrying — too little signal

_client = OpenAI(
    api_key=settings.openrouter_api_key,
    base_url="https://openrouter.ai/api/v1",
)


def retrieve_chunks(query: str, chat_session_id: str) -> list[RetrievedChunk]:
    query_embedding = embed_text(query)

    result = supabase_admin.rpc(
        "match_chunks",
        {
            "query_embedding": query_embedding,
            "session_id": chat_session_id,
            "match_count": settings.retrieval_top_k,
        },
    ).execute()

    for row in result.data:
        print(f"[DEBUG] chunk similarity={row['similarity']:.3f} content={row['content'][:80]!r}")

    return [
        RetrievedChunk(
            id=row["id"],
            document_id=row["document_id"],
            content=row["content"],
            page_number=row.get("page_number"),
            chunk_index=row["chunk_index"],
            similarity=row["similarity"],
        )
        for row in result.data
    ]


def _score_stats(chunks: list[RetrievedChunk]) -> tuple[float, float]:
    if not chunks:
        return 0.0, 0.0
    scores = [c.similarity for c in chunks]
    return scores[0], sum(scores) / len(scores)


def is_grounded(chunks: list[RetrievedChunk]) -> tuple[bool, float]:
    top_score, avg_score = _score_stats(chunks)
    if not chunks:
        return False, 0.0

    beats_average = top_score > avg_score
    clears_minimum = top_score >= MIN_ABSOLUTE_SCORE

    print(f"[DEBUG] top={top_score:.3f} avg={avg_score:.3f} beats_avg={beats_average} clears_min={clears_minimum}")

    return (beats_average or clears_minimum), top_score


def _reformulate_query(original_query: str) -> str:
    """
    Asks the LLM to rewrite the query into terms more likely to match
    document phrasing (e.g. expanding abbreviations, reordering terms
    to match how documents typically structure headings).
    """
    try:
        response = _client.chat.completions.create(
            model=settings.openrouter_models_list[0],
            max_tokens=60,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Rewrite the user's question into a short search query "
                        "optimized for matching document text via embedding search. "
                        "Expand abbreviations, use terms likely to appear verbatim in "
                        "structured documents (e.g. headings like 'Week 3' or 'Day 3'). "
                        "Reply with ONLY the rewritten query, nothing else."
                    ),
                },
                {"role": "user", "content": original_query},
            ],
        )
        rewritten = response.choices[0].message.content.strip()
        print(f"[DEBUG] reformulated query: {original_query!r} -> {rewritten!r}")
        return rewritten or original_query
    except Exception as e:
        print(f"[DEBUG] query reformulation failed: {e}")
        return original_query


def get_grounding_context(query: str, chat_session_id: str) -> tuple[bool, float, list[RetrievedChunk]]:
    """
    Single entry point rag_service.py calls. Retrieves chunks, checks
    groundedness, and if the result is borderline, reformulates the
    query and retries once before giving up.
    """
    chunks = retrieve_chunks(query, chat_session_id)
    grounded, top_score = is_grounded(chunks)

    if grounded:
        return True, top_score, chunks

    # Borderline band: some signal, but not enough to trust on the first pass.
    # Worth one corrective retry with a reformulated query.
    if top_score >= WEAK_BAND_FLOOR:
        reformulated = _reformulate_query(query)
        if reformulated != query:
            retry_chunks = retrieve_chunks(reformulated, chat_session_id)
            retry_grounded, retry_score = is_grounded(retry_chunks)
            if retry_grounded:
                return True, retry_score, retry_chunks

    return False, 0.0, []