"""
Document parsing, hashing, and Supabase Storage upload.
Handles PDF and DOCX, extracting page-aware text so citations can point
to a real page number.
"""

import hashlib
import io
from datetime import datetime, timezone

from pypdf import PdfReader
from docx import Document as DocxDocument

from supabase_client import supabase_admin


class ParsedPage:
    def __init__(self, page_number: int, text: str):
        self.page_number = page_number
        self.text = text


def hash_file(file_bytes: bytes) -> str:
    """SHA-256 hash used for duplicate detection within a chat session."""
    return hashlib.sha256(file_bytes).hexdigest()


def check_duplicate(chat_session_id: str, file_hash: str) -> bool:
    """True if this exact file was already uploaded in this session."""
    result = (
        supabase_admin.table("documents")
        .select("id")
        .eq("chat_session_id", chat_session_id)
        .eq("file_hash", file_hash)
        .neq("status", "failed")
        .execute()
    )
    return len(result.data) > 0


def parse_pdf(file_bytes: bytes) -> list[ParsedPage]:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(ParsedPage(page_number=i, text=text))
    return pages


def parse_docx(file_bytes: bytes) -> list[ParsedPage]:
    """
    DOCX has no native 'page' concept (pagination is a rendering detail),
    so we approximate pages by grouping paragraphs into fixed-size blocks.
    This keeps the citation format consistent with PDFs — 'page N' — even
    though it's really 'section N' under the hood. Documented in the
    chunking write-up.
    """
    doc = DocxDocument(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

    PARAGRAPHS_PER_PAGE = 8
    pages = []
    for i in range(0, len(paragraphs), PARAGRAPHS_PER_PAGE):
        block = paragraphs[i : i + PARAGRAPHS_PER_PAGE]
        page_number = (i // PARAGRAPHS_PER_PAGE) + 1
        pages.append(ParsedPage(page_number=page_number, text="\n".join(block)))
    return pages


def parse_document(filename: str, file_bytes: bytes) -> list[ParsedPage]:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return parse_pdf(file_bytes)
    elif lower.endswith(".docx"):
        return parse_docx(file_bytes)
    else:
        raise ValueError("Unsupported file type. Only PDF and DOCX are allowed.")


def upload_to_storage(user_id: str, chat_session_id: str, filename: str, file_bytes: bytes) -> str:
    """Uploads the original file to Supabase Storage, returns its storage path."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    storage_path = f"{user_id}/{chat_session_id}/{timestamp}_{filename}"

    supabase_admin.storage.from_("documents").upload(
        storage_path,
        file_bytes,
        file_options={"content-type": "application/octet-stream"},
    )
    return storage_path


def create_document_record(
    chat_session_id: str,
    user_id: str,
    filename: str,
    file_hash: str,
    storage_path: str,
    page_count: int,
    status: str = "processing",
) -> dict:
    result = (
        supabase_admin.table("documents")
        .insert(
            {
                "chat_session_id": chat_session_id,
                "user_id": user_id,
                "filename": filename,
                "file_hash": file_hash,
                "storage_path": storage_path,
                "page_count": page_count,
                "status": status,
            }
        )
        .execute()
    )
    return result.data[0]


def update_document_status(document_id: str, status: str) -> None:
    supabase_admin.table("documents").update({"status": status}).eq("id", document_id).execute()