from fastapi import APIRouter, Header, HTTPException

from supabase_client import supabase_admin, verify_user
from models import ChatSessionOut, ChatSessionRename

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _auth(authorization: str) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ")[1]
    user = verify_user(token)
    return user.id


@router.post("", response_model=ChatSessionOut)
def create_session(authorization: str = Header(...)):
    user_id = _auth(authorization)
    result = supabase_admin.table("chat_sessions").insert({"user_id": user_id, "title": "New Chat"}).execute()
    return result.data[0]


@router.get("", response_model=list[ChatSessionOut])
def list_sessions(authorization: str = Header(...)):
    user_id = _auth(authorization)
    result = (
        supabase_admin.table("chat_sessions")
        .select("*")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data


@router.patch("/{session_id}", response_model=ChatSessionOut)
def rename_session(session_id: str, body: ChatSessionRename, authorization: str = Header(...)):
    user_id = _auth(authorization)
    result = (
        supabase_admin.table("chat_sessions")
        .update({"title": body.title})
        .eq("id", session_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Session not found")
    return result.data[0]


@router.delete("/{session_id}")
def delete_session(session_id: str, authorization: str = Header(...)):
    user_id = _auth(authorization)
    supabase_admin.table("chat_sessions").delete().eq("id", session_id).eq("user_id", user_id).execute()
    return {"deleted": True}


@router.get("/{session_id}/messages")
def get_session_messages(session_id: str, authorization: str = Header(...)):
    _auth(authorization)
    result = (
        supabase_admin.table("chat_messages")
        .select("*")
        .eq("chat_session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data