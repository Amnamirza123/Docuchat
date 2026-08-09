from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
import json

from supabase_client import verify_user
from services.rag_service import stream_chat_response
from models import ChatRequest

router = APIRouter(prefix="/sessions/{session_id}/chat", tags=["chat"])


def _auth(authorization: str) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ")[1]
    user = verify_user(token)
    return user.id


@router.post("")
async def chat(session_id: str, body: ChatRequest, authorization: str = Header(...)):
    _auth(authorization)

    def event_generator():
        for index, text_delta in stream_chat_response(session_id, body.message):
            yield json.dumps({"index": index, "text": text_delta}) + "\n"
        yield json.dumps({"done": True}) + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )