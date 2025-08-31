BioMentor

AI-powered question bank builder for school subjects (starting with Biology).
Upload a PDF (textbook/notes), the app chunks and embeds it (Qdrant), then uses an open LLM (Qwen2.5) to generate grounded multiple-choice questions with explanations, difficulty, and topic tags. Questions are saved to PostgreSQL and exportable to CSV/JSON.

✨ Features

PDF ingestion → text chunking → vector store (Qdrant) with payloads

Question generation with Qwen/Qwen2.5-1.5B-Instruct (local CPU/MPS)

Quality gate + auto-retry (stem length, explanation length, difficulty whitelist)

Batch generation (generate N questions per doc)

Filtering & retrieval: latest, by document, with topic/difficulty filters

Export to CSV/JSON for easy printing/sharing

Schema migrations with Alembic (locked, versioned)

🧱 Architecture (backend MVP)
frontend/                  # (placeholder Next.js app, to be built)
backend/
  app/
    api/
      routes_ingest.py     # POST /ingest
      routes_qgen.py       # /qgen/* (generate, batch, preview_context)
      routes_questions.py  # /questions/* (read/export)
    models/
      question.py          # SQLAlchemy model
    services/
      db.py                # SQLAlchemy engine/session + init
      ingestion_service.py # pdf → chunks → embeddings → Qdrant upsert
      qgen_service.py      # Qdrant → context → LLM → JSON → quality gate
    config.py              # Pydantic settings (reads .env)
    main.py                # FastAPI app, routers, CORS, startup
  alembic/
    versions/              # migration files
    env.py                 # Alembic setup
  .env                     # local secrets (ignored; use .env.example)
  requirements.txt
README.md

🚀 Quickstart (local dev)
Prereqs

Python 3.9+ (3.9 used currently)

PostgreSQL 14+ (local)

Qdrant (local server on 127.0.0.1:6333)

macOS users: Apple Silicon works (MPS shown in logs)

1) Clone & install
git clone https://github.com/<your_user>/<your_repo>.git
cd <your_repo>/backend

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt


If you see numpy / onnxruntime errors with fastembed, pin numpy<2:

pip install "numpy<2" onnxruntime==1.16.3

2) Start Qdrant

Run via Docker (recommended):

docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant:v1.8.2


We used client qdrant-client==1.15.x with server 1.8.2.
If you see a version warning, either:

set check_compatibility=False when constructing the client, or

align client/server versions.

3) Create .env
# backend/.env
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=biomentor
DB_USER=********
DB_PASSWORD=********
ENVIRONMENT=development


(Commit a sanitized backend/.env.example with blank values.)

4) Init DB & run migrations
# from backend/
alembic upgrade head

5) Run the API
# from backend/
python -m uvicorn app.main:app --reload
# → http://127.0.0.1:8000

🔌 Endpoints (cURL)
Health
curl http://127.0.0.1:8000/health

1) Ingest a PDF

Uploads and indexes chunks into Qdrant (collection=notes).

curl -X POST -F "file=@$HOME/Downloads/your.pdf" \
  http://127.0.0.1:8000/ingest/
# → {"docId":"<UUID>","count":<N_CHUNKS>}

2) Preview the grounded context (no LLM call)
curl "http://127.0.0.1:8000/qgen/preview_context?docId=<DOC_ID>&k=8"


Optional focused preview by query (semantic filter):

curl "http://127.0.0.1:8000/qgen/preview_context_query?docId=<DOC_ID>&query=protozoa&k=8"

3) Generate & save ONE question from a doc

Quality gate + auto-retry included. Saves to Postgres (questions).

curl -X POST http://127.0.0.1:8000/qgen/from_doc_and_save \
  -H "Content-Type: application/json" \
  -d '{"docId":"<DOC_ID>","k":8}'
# → {"id":"<QUESTION_UUID>","saved":true}


Semantic focus:

curl -X POST http://127.0.0.1:8000/qgen/from_doc_query_and_save \
  -H "Content-Type: application/json" \
  -d '{"docId":"<DOC_ID>","query":"protozoa","k":8}'

4) Batch generate & save N questions
curl -X POST http://127.0.0.1:8000/qgen/from_doc_batch_and_save \
  -H "Content-Type: application/json" \
  -d '{"docId":"<DOC_ID>","n":5,"k":8}'
# → { "saved": [...], "rejected": [...] }

5) Read/Filter
# latest N
curl "http://127.0.0.1:8000/questions/latest?limit=10"

# by document
curl "http://127.0.0.1:8000/questions/by_doc/<DOC_ID>?limit=5"

# filter
curl "http://127.0.0.1:8000/questions/latest?topic=protozoa&difficulty=medium"

6) Export (CSV/JSON)
# CSV
curl -OJ "http://127.0.0.1:8000/questions/export?format=csv"
# filters
curl -OJ "http://127.0.0.1:8000/questions/export?docId=<DOC_ID>&difficulty=medium"

# JSON
curl "http://127.0.0.1:8000/questions/export?format=json&topic=protozoa" | jq

🗄️ Database
Table: questions
column	type	notes
id	UUID PK	generated server-side
stem	TEXT	the question
options	JSONB	exactly 4 options
answer	TEXT	must be one of options
explanation	TEXT	2–4 sentence rationale
difficulty	TEXT	one of easy|medium|hard
topic	TEXT	short noun phrase
source_doc_id	TEXT	doc id returned by /ingest
created_at	TIMESTAMP	default now()
Migrations

f6ba3d4af7b8 – baseline questions table

81d6158f037c – add explanation, difficulty, topic

Commands:

# create a new migration (after model changes)
alembic revision -m "add xyz" --autogenerate

# upgrade / downgrade
alembic upgrade head
alembic downgrade -1

# show status
alembic current
alembic heads
alembic history
alembic show <REV_ID>

🧠 LLM & Generation

Model: Qwen/Qwen2.5-1.5B-Instruct (open; downloads ~3 GB on first run)

Pipeline: transformers.pipeline("text-generation") with deterministic params:

do_sample=False, temperature=0.0, top_p=1.0

Prompt instructs the model to return STRICT JSON:

{
  "stem": "...",
  "options": ["A","B","C","D"],
  "answer": "A",
  "explanation": "...",
  "difficulty": "easy|medium|hard",
  "topic": "..."
}


Quality gate (auto-retry up to 3 total attempts):

stem ≥ 20 chars

explanation ≥ 40 chars

options length == 4 and answer ∈ options

difficulty ∈ {easy, medium, hard}

topic length ≥ 3

🧾 Environment Variables

backend/.env:

DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=biomentor
DB_USER=********
DB_PASSWORD=********
ENVIRONMENT=development


Keep real .env ignored; commit backend/.env.example.

🧪 Troubleshooting

NotOpenSSLWarning (urllib3 + LibreSSL on macOS): harmless in local dev.

Qdrant client/server version warning:
Align versions, or create client with check_compatibility=False.

First LLM run downloads 3GB: expected. Subsequent runs use local cache.

numpy / onnxruntime / fastembed errors:
Use pip install "numpy<2" onnxruntime==1.16.3.

Python 3.9 type hints: use Optional[str] instead of str | None.

🗺️ Roadmap

Frontend: document browser, question filter UI, quiz mode

Explanations reviewer UI; edit/save

Teacher-friendly exports (docx/pdf quiz sheets, answer keys)

Authentication + per-teacher workspaces

Advanced retrieval (hybrid search, re-ranking)

📝 License

MIT (or your choice). Add a LICENSE file.

Maintainers

You! PRs/issues welcome.
If you want, I can also write a minimal CONTRIBUTING.md and a Makefile (make dev, make migrate, make seed) next.