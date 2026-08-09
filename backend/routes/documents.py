from fastapi import APIRouter, Header, HTTPException, UploadFile, File

from supabase_client import verify_user
from services.document_service import (
    hash_file,
    check_duplicate,
    parse_document,
    upload_to_storage,
    create_document_record,
    update_document_status,
)
from services.chunking_service import chunk_document
from services.embedding_service import embed_batch
from supabase_client import supabase_admin
from models import DocumentUploadResponse

router = APIRouter(prefix="/sessions/{session_id}/documents", tags=["documents"])


def _auth(authorization: str) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ")[1]
    user = verify_user(token)
    return user.id


@router.post("", response_model=DocumentUploadResponse)
async def upload_document(session_id: str, file: UploadFile = File(...), authorization: str = Header(...)):
    user_id = _auth(authorization)

    if not (file.filename.lower().endswith(".pdf") or file.filename.lower().endswith(".docx")):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    file_bytes = await file.read()
    file_hash = hash_file(file_bytes)

    if check_duplicate(session_id, file_hash):
        # Create a lightweight record marked duplicate — frontend shows "duplicate doc"
        doc = create_document_record(
            chat_session_id=session_id,
            user_id=user_id,
            filename=file.filename,
            file_hash=file_hash,
            storage_path="",
            page_count=0,
            status="duplicate",
        )
        return DocumentUploadResponse(document=doc, message="This document was already uploaded in this chat.")

    # Create the record immediately as "processing" so the frontend can show status right away
    storage_path = upload_to_storage(user_id, session_id, file.filename, file_bytes)
    doc = create_document_record(
        chat_session_id=session_id,
        user_id=user_id,
        filename=file.filename,
        file_hash=file_hash,
        storage_path=storage_path,
        page_count=0,
        status="processing",
    )

    try:
        pages = parse_document(file.filename, file_bytes)
        chunks = chunk_document(pages)

        if not chunks:
            update_document_status(doc["id"], "failed")
            raise HTTPException(status_code=422, detail="No extractable text found in this document")

        embeddings = embed_batch([c.content for c in chunks])

        rows = [
            {
                "document_id": doc["id"],
                "chat_session_id": session_id,
                "content": chunk.content,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "embedding": embedding,
            }
            for chunk, embedding in zip(chunks, embeddings)
        ]
        supabase_admin.table("chunks").insert(rows).execute()

        supabase_admin.table("documents").update(
            {"status": "successful", "page_count": len(pages)}
        ).eq("id", doc["id"]).execute()

        doc["status"] = "successful"
        doc["page_count"] = len(pages)

        return DocumentUploadResponse(document=doc, message="Document processed successfully.")

    except HTTPException:
        raise
    except Exception as e:
        update_document_status(doc["id"], "failed")
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")


@router.get("")
def list_documents(session_id: str, authorization: str = Header(...)):
    _auth(authorization)
    result = (
        supabase_admin.table("documents")
        .select("*")
        .eq("chat_session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


@router.delete("/{document_id}")
def delete_document(session_id: str, document_id: str, authorization: str = Header(...)):
    _auth(authorization)
    doc = supabase_admin.table("documents").select("storage_path").eq("id", document_id).execute()
    if doc.data and doc.data[0]["storage_path"]:
        supabase_admin.storage.from_("documents").remove([doc.data[0]["storage_path"]])
    supabase_admin.table("documents").delete().eq("id", document_id).execute()
    return {"deleted": True}