import uuid
import fitz  # PyMuPDF
from typing import List, Dict
from fastembed import TextEmbedding
import qdrant_client
from qdrant_client.models import Distance, VectorParams, PointStruct

COLLECTION = "notes"
EMBED_DIM = 384  # fastembed default

# singletons
_embedder = TextEmbedding()
_qdrant = qdrant_client.QdrantClient(host="127.0.0.1", port=6333)

def _ensure_collection():
    try:
        _qdrant.get_collection(COLLECTION)
    except Exception:
        _qdrant.recreate_collection(
            COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
def _chunk_plain_text(text: str) -> List[str]:
    # simple MVP splitter: sentence-ish by periods; trim empties
    parts = [p.strip() for p in text.split(".") if p.strip()]
    # keep short chunks reasonable
    return [p if p.endswith(".") else p + "." for p in parts]

async def ingest_pdf(file) -> Dict[str, str]:
    _ensure_collection()
    data = await file.read()
    doc = fitz.open(stream=data, filetype="pdf")

    chunks = []
    for page_no, page in enumerate(doc, start=1):
        t = page.get_text("text")
        if not t:
            continue
        for idx, chunk in enumerate(_chunk_plain_text(t)):
            chunks.append({"page": page_no, "idx": idx, "text": chunk})

    if not chunks:
        return {"docId": None, "count": 0}

    vectors = list(_embedder.embed([c["text"] for c in chunks]))
    doc_id = str(uuid.uuid4())

    points = [
    PointStruct(
        id=str(uuid.uuid4()),  # <- use a real UUID for each point
        vector=[float(x) for x in vec],  # <- ensure plain floats (not numpy types)
        payload={"doc_id": doc_id, "page": c["page"], "idx": c["idx"], "text": c["text"]},
    )
    for i, (vec, c) in enumerate(zip(vectors, chunks))
]
    _qdrant.upsert(collection_name=COLLECTION, points=points)
    return {"docId": doc_id, "count": len(points)}