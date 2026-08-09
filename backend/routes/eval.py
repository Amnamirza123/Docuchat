from fastapi import APIRouter, Header, HTTPException
from pathlib import Path

from supabase_client import verify_user
from services.eval_service import run_eval, report_to_markdown

router = APIRouter(prefix="/sessions/{session_id}/eval", tags=["eval"])

REPORT_PATH = Path(__file__).parent.parent.parent / "eval" / "report.md"


def _auth(authorization: str) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ")[1]
    return verify_user(token).id


@router.post("/run")
def run_evaluation(session_id: str, authorization: str = Header(...)):
    _auth(authorization)
    report = run_eval(session_id)
    markdown = report_to_markdown(report)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(markdown)

    return report