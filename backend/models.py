"""
Pydantic schemas shared across routes and services.
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel


# =========================================================
# Sessions
# =========================================================
class ChatSessionOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ChatSessionRename(BaseModel):
    title: str


# =========================================================
# Documents
# =========================================================
DocumentStatus = Literal["processing", "successful", "duplicate", "failed"]


class DocumentOut(BaseModel):
    id: str
    filename: str
    status: DocumentStatus
    page_count: Optional[int] = None
    created_at: datetime


class DocumentUploadResponse(BaseModel):
    document: DocumentOut
    message: str


# =========================================================
# Chat
# =========================================================
class ChatRequest(BaseModel):
    message: str


class Citation(BaseModel):
    document_id: str
    filename: str
    page_number: Optional[int] = None
    chunk_index: int


class ChatMessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    is_grounded: Optional[bool] = None
    groundedness_score: Optional[float] = None
    citations: list[Citation] = []
    created_at: datetime


# =========================================================
# Retrieval (internal use between services, not exposed directly)
# =========================================================
class RetrievedChunk(BaseModel):
    id: str
    document_id: str
    content: str
    page_number: Optional[int] = None
    chunk_index: int
    similarity: float


# =========================================================
# Evaluation
# =========================================================
class EvalQuestion(BaseModel):
    question: str
    expected_answer_contains: Optional[str] = None
    should_be_grounded: bool


class EvalResultRow(BaseModel):
    question: str
    answer: str
    is_grounded: bool
    expected_grounded: bool
    groundedness_score: Optional[float] = None
    retrieval_relevant: bool
    citations: list[Citation] = []


class EvalReport(BaseModel):
    total_questions: int
    grounded_correct: int
    retrieval_relevance_rate: float
    hallucination_rate: float
    rows: list[EvalResultRow]