# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.api import routes_ingest, routes_qgen
from app.services.db import init_db, get_session
from app.api import routes_questions  # add this

app = FastAPI(title="BioMentor API")

@app.on_event("startup")
def _startup():
    print("[APP] startup: calling init_db() …")
    init_db()
    print("[APP] startup: init_db() done.")

@app.on_event("shutdown")
def _shutdown():
    print("[APP] shutdown: bye 👋")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

@app.get("/health")
def health():
    try:
        with get_session() as s:
            s.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    
@app.get("/db/health")
def db_health():
    try:
        with get_session() as s:
            s.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/questions/count")
def questions_count():
    with get_session() as s:
        n = s.execute(text("SELECT COUNT(*) FROM questions")).scalar_one()
        return {"count": n}

@app.get("/questions/latest")
def questions_latest(limit: int = 5):
    with get_session() as s:
        rows = s.execute(text("""
            SELECT id::text, stem, answer, created_at
            FROM questions
            ORDER BY created_at DESC
            LIMIT :lim
        """), {"lim": limit}).mappings().all()
        return {"items": list(rows)}

app.include_router(routes_ingest.router, prefix="/ingest", tags=["Ingestion"])
app.include_router(routes_questions.router, prefix="/questions", tags=["Questions"])
app.include_router(routes_qgen.router, prefix="/qgen", tags=["Question Generation"])
print("[APP] Routers mounted: /ingest, /qgen")
