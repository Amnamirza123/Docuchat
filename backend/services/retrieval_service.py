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