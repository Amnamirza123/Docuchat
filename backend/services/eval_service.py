"""
Runs the 15-question test set against the RAG pipeline and produces a
groundedness/retrieval report.
"""

import json
from pathlib import Path

from services.retrieval_service import get_grounding_context
from services.rag_service import _build_context_block, SYSTEM_PROMPT_GROUNDED, SYSTEM_PROMPT_PLAIN
from openai import OpenAI
from config import settings
from models import EvalQuestion, EvalResultRow, EvalReport, Citation

_client = OpenAI(
    api_key=settings.openrouter_api_key,
    base_url="https://openrouter.ai/api/v1",
)

QUESTIONS_PATH = Path(__file__).parent.parent / "tests" / "eval_questions.json"


def _load_questions() -> list[EvalQuestion]:
    with open(QUESTIONS_PATH, "r") as f:
        raw = json.load(f)
    return [EvalQuestion(**q) for q in raw]


def _get_full_response(system_prompt: str, question: str) -> str:
    response = _client.chat.completions.create(
        model=settings.openrouter_model,
        max_tokens=800,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    )
    return response.choices[0].message.content

def run_eval(chat_session_id: str) -> EvalReport:
    questions = _load_questions()
    rows: list[EvalResultRow] = []

    grounded_correct = 0
    retrieval_relevant_count = 0

    for q in questions:
        grounded, top_score, chunks = get_grounding_context(q.question, chat_session_id)

        if grounded:
            context = _build_context_block(chunks)
            system_prompt = SYSTEM_PROMPT_GROUNDED.format(context=context)
        else:
            system_prompt = SYSTEM_PROMPT_PLAIN

        answer = _get_full_response(system_prompt, q.question)

        # Correctness: did grounding match what we expected?
        grounded_matches_expected = grounded == q.should_be_grounded
        if grounded_matches_expected:
            grounded_correct += 1

        # Retrieval relevance: when grounding was expected, did we retrieve
        # chunks AND actually mark it grounded (i.e. found the right thing)?
        retrieval_relevant = (not q.should_be_grounded) or (q.should_be_grounded and grounded)
        if retrieval_relevant:
            retrieval_relevant_count += 1

        citations = []
        if grounded:
            citations = [
                Citation(
                    document_id=c.document_id,
                    filename="(see documents table)",
                    page_number=c.page_number,
                    chunk_index=c.chunk_index,
                )
                for c in chunks
            ]

        rows.append(
            EvalResultRow(
                question=q.question,
                answer=answer,
                is_grounded=grounded,
                expected_grounded=q.should_be_grounded,
                groundedness_score=top_score if grounded else None,
                retrieval_relevant=retrieval_relevant,
                citations=citations,
            )
        )

    total = len(questions)
    hallucination_rate = 1 - (grounded_correct / total) if total else 0.0

    return EvalReport(
        total_questions=total,
        grounded_correct=grounded_correct,
        retrieval_relevance_rate=retrieval_relevant_count / total if total else 0.0,
        hallucination_rate=hallucination_rate,
        rows=rows,
    )


def report_to_markdown(report: EvalReport) -> str:
    lines = [
        "# DocuChat Evaluation Report",
        "",
        f"- Total questions: {report.total_questions}",
        f"- Grounding correctness: {report.grounded_correct}/{report.total_questions}",
        f"- Retrieval relevance rate: {report.retrieval_relevance_rate:.0%}",
        f"- Hallucination rate: {report.hallucination_rate:.0%}",
        "",
        "## Per-question results",
        "",
        "| # | Question | Expected Grounded | Actual Grounded | Score | Retrieval Relevant |",
        "|---|----------|--------------------|------------------|-------|---------------------|",
    ]

    for i, row in enumerate(report.rows, start=1):
        score = f"{row.groundedness_score:.2f}" if row.groundedness_score is not None else "-"
        lines.append(
            f"| {i} | {row.question[:60]} | {row.expected_grounded} | {row.is_grounded} | {score} | {row.retrieval_relevant} |"
        )

    return "\n".join(lines)