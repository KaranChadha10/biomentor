# app/api/routes_questions.py
from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc
from app.services.db import get_session
from app.models.question import Question
from fastapi.responses import StreamingResponse, JSONResponse
import io, csv

router = APIRouter()

def _row_to_dict(q: Question) -> Dict[str, Any]:
    return {
        "id": str(q.id),
        "stem": q.stem,
        "options": q.options,
        "answer": q.answer,
        "source_doc_id": q.source_doc_id,
        "explanation": q.explanation,
        "difficulty": q.difficulty,
        "topic": q.topic,
        "created_at": q.created_at,
    }


@router.get("/latest")
def latest(limit: int = 10,
           topic: Optional[str] = None,
           difficulty: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_session() as s:
        stmt = select(Question).order_by(desc(Question.created_at)).limit(limit)
        if topic:
            stmt = stmt.filter(Question.topic == topic)
        if difficulty:
            stmt = stmt.filter(Question.difficulty == difficulty)
        rows = s.execute(stmt).scalars().all()
        return [_row_to_dict(q) for q in rows]
    
@router.get("/by_doc/{doc_id}")
def by_doc(doc_id: str,
           limit: int = 20,
           topic: Optional[str] = None,
           difficulty: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_session() as s:
        stmt = (
            select(Question)
            .where(Question.source_doc_id == doc_id)
            .order_by(desc(Question.created_at))
            .limit(limit)
        )
        if topic:
            stmt = stmt.filter(Question.topic == topic)
        if difficulty:
            stmt = stmt.filter(Question.difficulty == difficulty)
        rows = s.execute(stmt).scalars().all()
        return [_row_to_dict(q) for q in rows]
    
@router.get("/{qid}")
def get_one(qid: str) -> Dict[str, Any]:
    with get_session() as s:
        row = s.get(Question, qid)
        if not row:
            raise HTTPException(status_code=404, detail="Question not found")
        return _row_to_dict(row)
    
@router.get("/count")
def count():
    with get_session() as s:
        n = s.execute(select(func.count(Question.id))).scalar_one()
        return {"count": n}
    
@router.get("/by_doc")
def by_doc(docId: str, limit: int = 50):
    with get_session() as s:
        rows = s.execute(
            select(Question)
            .where(Question.source_doc_id == docId)
            .order_by(desc(Question.created_at))
            .limit(limit)
        ).scalars().all()
        return [
            {
                "id": str(q.id),
                "stem": q.stem,
                "answer": q.answer,
                "options": q.options,
                "source_doc_id": q.source_doc_id,
                "created_at": q.created_at,
            }
            for q in rows
        ]
    
@router.get("/export")
def export_questions(
    format: str = "csv",
    limit: int = 1000,
    docId: Optional[str] = None,
    topic: Optional[str] = None,
    difficulty: Optional[str] = None,
):
    """Export questions as CSV (default) or JSON with optional filters."""
    with get_session() as s:
        stmt = select(Question).order_by(desc(Question.created_at)).limit(limit)
        if docId:
            stmt = stmt.filter(Question.source_doc_id == docId)
        if topic:
            stmt = stmt.filter(Question.topic == topic)
        if difficulty:
            stmt = stmt.filter(Question.difficulty == difficulty)
        rows = s.execute(stmt).scalars().all()

        # JSON export
        if format.lower() == "json":
            payload = [
                {
                    "id": str(q.id),
                    "stem": q.stem,
                    "options": q.options,
                    "answer": q.answer,
                    "explanation": q.explanation,
                    "difficulty": q.difficulty,
                    "topic": q.topic,
                    "source_doc_id": q.source_doc_id,
                    "created_at": q.created_at.isoformat() if q.created_at else None,
                }
                for q in rows
            ]
            return JSONResponse(payload)

        # CSV export (default)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "stem", "option_A", "option_B", "option_C", "option_D",
            "answer", "explanation", "difficulty", "topic", "source_doc_id", "created_at"
        ])
        for q in rows:
            opts = (q.options or [])
            a = opts[0] if len(opts) > 0 else ""
            b = opts[1] if len(opts) > 1 else ""
            c = opts[2] if len(opts) > 2 else ""
            d = opts[3] if len(opts) > 3 else ""
            writer.writerow([
                str(q.id),
                q.stem or "",
                a, b, c, d,
                q.answer or "",
                q.explanation or "",
                q.difficulty or "",
                q.topic or "",
                q.source_doc_id or "",
                q.created_at.isoformat() if q.created_at else "",
            ])
        output.seek(0)
        filename = "questions.csv" if not (docId or topic or difficulty) else \
            f"questions_{docId or topic or difficulty}.csv"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(iter([output.read()]), media_type="text/csv", headers=headers)