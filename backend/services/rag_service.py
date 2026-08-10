"""
Core RAG orchestration: decides doc-context vs. plain chat, builds the
prompt, streams the LLM response, and saves the resulting message
(with groundedness score + citations) back to chat_messages.

Streaming dedup guard: each streamed event carries a monotonic index.
The frontend hook only appends a chunk if its index is greater than the
last one it rendered — so a retried/replayed event can never duplicate
text on screen, which is the "no duplication" requirement.

Model fallback: tries each model in settings.openrouter_models_list in
order. If one is rate-limited or errors out, it moves to the next
before giving up — so a single exhausted free model doesn't break chat.

Safety-metadata guard: openrouter/free randomly picks an underlying free
model per request. Occasionally the picked model returns raw
safety-classifier output (e.g. "User Safety: safe Response Safety: safe")
instead of a real answer. That's detected and treated as a failure worth
retrying with the next model in the list, rather than shown to the user.
"""

import json
from openai import OpenAI

from config import settings
from supabase_client import supabase_admin
from services.retrieval_service import get_grounding_context
from models import Citation

_client = OpenAI(
    api_key=settings.openrouter_api_key,
    base_url="https://openrouter.ai/api/v1",
)

SYSTEM_PROMPT_GROUNDED = """You are DocuChat, an assistant that answers questions using the provided document excerpts.

Rules:
1. Answer ONLY using the information in the excerpts below. Do not use outside knowledge to fill gaps.
2. When you state a fact from an excerpt, note which excerpt it came from using its [N] marker.
3. If the excerpts don't fully answer the question, say what's missing rather than guessing.
4. Format answers with markdown — use tables when comparing structured information, bullet points for lists.
5. Be direct and concise. Do not pad the answer with filler.

Document excerpts:
{context}
"""

SYSTEM_PROMPT_PLAIN = """You are DocuChat, a helpful conversational assistant.

The user's message does not appear to relate to any uploaded document, or no documents have been uploaded yet in this chat. Respond normally and conversationally. Use markdown formatting (tables, lists) where it helps clarity. Do not claim to reference documents you don't have grounded context for.
"""


def _build_context_block(chunks) -> str:
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        page_info = f", page {chunk.page_number}" if chunk.page_number else ""
        blocks.append(f"[{i}]{page_info}\n{chunk.content}")
    return "\n\n".join(blocks)


def _filenames_for_documents(document_ids: list[str]) -> dict[str, str]:
    if not document_ids:
        return {}
    result = (
        supabase_admin.table("documents")
        .select("id, filename")
        .in_("id", document_ids)
        .execute()
    )
    return {row["id"]: row["filename"] for row in result.data}


def _looks_like_safety_metadata(text: str) -> bool:
    """Detects the 'User Safety: safe Response Safety: safe' style glitch
    some free models occasionally return instead of a real answer."""
    return "Safety:" in text and len(text) < 100


def stream_chat_response(chat_session_id: str, user_message: str):
    """
    Generator yielding (index, text_delta) tuples for SSE streaming.
    After the full response is generated, saves the assistant message
    (with groundedness + citations) to chat_messages.
    """
    grounded, top_score, chunks = get_grounding_context(user_message, chat_session_id)

    if grounded:
        context = _build_context_block(chunks)
        system_prompt = SYSTEM_PROMPT_GROUNDED.format(context=context)
    else:
        system_prompt = SYSTEM_PROMPT_PLAIN

    history_result = (
        supabase_admin.table("chat_messages")
        .select("role, content")
        .eq("chat_session_id", chat_session_id)
        .order("created_at", desc=False)
        .limit(20)
        .execute()
    )
    history = [{"role": row["role"], "content": row["content"]} for row in history_result.data]
    history.append({"role": "user", "content": user_message})

    messages = [{"role": "system", "content": system_prompt}] + history

    full_text = ""
    index = 0
    last_error = None

    for model_name in settings.openrouter_models_list:
        try:
            print(f"[DEBUG] Trying model: {model_name}")
            stream = _client.chat.completions.create(
                model=model_name,
                max_tokens=1500,
                messages=messages,
                stream=True,
            )

            attempt_text = ""
            buffered_deltas = []
            for event in stream:
                delta = event.choices[0].delta.content
                if delta:
                    attempt_text += delta
                    buffered_deltas.append(delta)

            got_any_content = bool(attempt_text)
            print(f"[DEBUG] {model_name} got_any_content={got_any_content}")

            if got_any_content and not _looks_like_safety_metadata(attempt_text):
                # Good response — now actually stream it out to the client.
                for delta in buffered_deltas:
                    full_text += delta
                    yield index, delta
                    index += 1
                last_error = None
                break
            elif got_any_content:
                print(f"[DEBUG] {model_name} returned safety metadata instead of real content, retrying")
                continue

        except Exception as e:
            print(f"[DEBUG] {model_name} failed with: {e}")
            last_error = e
            continue

    if not full_text:
        error_message = "I'm having trouble reaching any available model right now. Please try again in a moment."
        yield 0, error_message
        full_text = error_message

    citations = []
    if grounded:
        document_ids = list({c.document_id for c in chunks})
        filenames = _filenames_for_documents(document_ids)
        citations = [
            Citation(
                document_id=c.document_id,
                filename=filenames.get(c.document_id, "unknown"),
                page_number=c.page_number,
                chunk_index=c.chunk_index,
            )
            for c in chunks
        ]

    supabase_admin.table("chat_messages").insert(
        {"chat_session_id": chat_session_id, "role": "user", "content": user_message}
    ).execute()

    supabase_admin.table("chat_messages").insert(
        {
            "chat_session_id": chat_session_id,
            "role": "assistant",
            "content": full_text,
            "is_grounded": grounded,
            "groundedness_score": top_score if grounded else None,
            "citations": json.dumps([c.model_dump() for c in citations]),
        }
    ).execute()