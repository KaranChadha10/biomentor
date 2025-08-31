from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException
from typing import Optional, List
from app.services import qgen_service
from app.services.db import get_session
from app.models.question import Question

router = APIRouter()

class BatchReq(BaseModel):
    docId: str = Field(..., alias="docId")
    n: int = 5
    k: int = 8
    query: Optional[str] = None  # when present → semantic focus

class FromDocQueryReq(BaseModel):
    docId: str = Field(..., alias="docId")
    query: str
    k: int = 8

@router.get("/preview_context_query")
def preview_context_query(docId: str, query: str, k: int = 8):
    return qgen_service.preview_context_query(doc_id=docId, query=query, k=k)

@router.post("/from_doc_batch_and_save")
async def from_doc_batch_and_save(body: BatchReq):
    items = await qgen_service.generate_batch_from_doc(
        doc_id=body.docId, n=body.n, query=body.query, k=body.k
    )
    if not items:
        raise HTTPException(status_code=404, detail="No questions generated.")

    valid = []
    rejected = []
    for d in items:
        if not isinstance(d, dict):
            rejected.append({"item": d, "reason": "not a dict"})
            continue
        if "error" in d:
            rejected.append({"item": d, "reason": d["error"]})
            continue
        # minimal schema sanity (qgen_service already quality-gates, this is just defensive)
        needed = ("stem", "options", "answer", "explanation", "difficulty", "topic")
        if not all(k in d for k in needed):
            rejected.append({"item": d, "reason": "missing required fields"})
            continue
        if not isinstance(d["options"], list) or len(d["options"]) != 4:
            rejected.append({"item": d, "reason": "options must have length 4"})
            continue
        if d["answer"] not in d["options"]:
            rejected.append({"item": d, "reason": "answer not in options"})
            continue
        valid.append(d)

    if not valid:
        # nothing to save—surface why
        raise HTTPException(status_code=422, detail={"message": "All items failed quality checks", "rejected": rejected})

    saved: List[Question] = []
    try:
        with get_session() as s:
            for d in valid:
                q = Question(
                    stem=d["stem"],
                    options=d["options"],
                    answer=d["answer"],
                    explanation=d["explanation"],
                    difficulty=d["difficulty"],
                    topic=d["topic"],
                    source_doc_id=d.get("source_doc_id") or body.docId,
                )
                s.add(q)
                saved.append(q)
            s.commit()
            for q in saved:
                s.refresh(q)
    except Exception as e:
        # rollback is automatic on context exit if commit didn't happen, but be explicit just in case
        raise HTTPException(status_code=500, detail=f"DB error while saving batch: {e}")

    return {
        "saved": [
            {
                "id": str(q.id),
                "stem": q.stem,
                "answer": q.answer,
                "options": q.options,
                "explanation": q.explanation,
                "difficulty": q.difficulty,
                "topic": q.topic,
                "source_doc_id": q.source_doc_id,
                "created_at": q.created_at,
            }
            for q in saved
        ],
        "rejected": rejected,  # each has {"item": <raw>, "reason": "..."}
    }