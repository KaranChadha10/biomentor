# app/services/qgen_service.py
import json
from typing import Dict, Any, List
from typing import Tuple


from fastapi import HTTPException
from transformers import AutoTokenizer, pipeline
import asyncio
import re
from typing import Optional

try:
    from fastembed import TextEmbedding
    _embedder = TextEmbedding()
    def _embed_one(text: str):
        return list(_embedder.embed([text]))[0]
except Exception:
    # fallback if fastembed/onnxruntime not available
    from sentence_transformers import SentenceTransformer
    _st = SentenceTransformer("all-MiniLM-L6-v2")
    def _embed_one(text: str):
        return _st.encode([text], normalize_embeddings=True)[0].tolist()

from qdrant_client.models import Filter, FieldCondition, MatchValue

VALID_DIFFICULTIES = {"easy", "medium", "hard"}

# Strengthen the JSON schema prompt to include explanation/difficulty/topic
JSON_PROMPT = """You are an exam item writer. Output STRICT JSON only (no prose).
Schema:
{{
  "stem": "string",
  "options": ["A","B","C","D"],
  "answer": "A",
  "explanation": "string",
  "difficulty": "easy|medium|hard",
  "topic": "string"
}}
Rules:
- Use exactly 4 options.
- Ensure the correct answer is one of the options.
- Use ONLY the provided Context; do not invent facts.
- "explanation" must be 2–4 sentences and justify the correct answer from Context.
- "difficulty" must be one of: easy, medium, hard.
- "topic" should be a short noun phrase (e.g., "protozoa", "cell organelles").
Context:
{context}
Return only the JSON object.
"""

def _normalize(item: Dict[str, Any]) -> Dict[str, Any]:
    """Make small fixes: trim strings, lowercase difficulty, coerce list types."""
    if not isinstance(item, dict):
        return item
    item["stem"] = (item.get("stem") or "").strip()
    item["options"] = [str(x).strip() for x in (item.get("options") or [])][:4]
    item["answer"] = (item.get("answer") or "").strip()
    item["explanation"] = (item.get("explanation") or "").strip()
    diff = (item.get("difficulty") or "").strip().lower()
    item["difficulty"] = diff
    item["topic"] = (item.get("topic") or "").strip()
    return item

def _is_valid(item: Dict[str, Any]) -> Tuple[bool, str]:
    """Quality gate: lengths, presence, and difficulty whitelist."""
    if not isinstance(item, dict):
        return False, "not a dict"

    stem = item.get("stem") or ""
    opts = item.get("options") or []
    ans  = item.get("answer") or ""
    expl = item.get("explanation") or ""
    diff = (item.get("difficulty") or "").lower()
    topic = item.get("topic") or ""

    if len(stem) < 20:
        return False, "stem too short (<20 chars)"
    if not isinstance(opts, list) or len(opts) != 4:
        return False, "options must be length 4"
    if ans not in opts:
        return False, "answer must be one of options"
    if len(expl) < 40:
        return False, "explanation too short (<40 chars)"
    if diff not in VALID_DIFFICULTIES:
        return False, "difficulty must be easy|medium|hard"
    if len(topic) < 3:
        return False, "topic too short"
    return True, "ok"

def _semantic_chunks(doc_id: str, query: str, k: int = 8) -> List[dict]:
    """Vector search within a single doc using query embedding."""
    vec = [float(x) for x in _embed_one(query)]
    flt = Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
    hits = _qdrant.search(
        collection_name=_QDRANT_COLLECTION,
        query_vector=vec,
        limit=k,
        with_payload=True,
        query_filter=flt,
    )
    chunks = []
    for h in hits:
        p = h.payload or {}
        if "text" in p:
            chunks.append({"text": p["text"], "page": p.get("page"), "idx": p.get("idx")})
    return chunks

async def generate_from_doc_query(doc_id: str, query: str, k: int = 8) -> Dict[str, Any]:
    """Use query-focused chunks → prompt Qwen → return STRICT JSON."""
    chunks = _semantic_chunks(doc_id, query, k=k)
    if not chunks:
        return {"error": f"No chunks found for docId={doc_id} with query='{query}'"}

    context = "\n".join([f"(p{c['page']}#{c['idx']}): {c['text']}" for c in chunks])
    prompt = JSON_PROMPT.format(context=context)
    out = generate(
        prompt,
        max_new_tokens=220,
        do_sample=False,
        temperature=0.0,
        top_p=1.0,
        return_full_text=False,
    )[0]["generated_text"]
    data = _parse_json_safely(out)
    data["source_doc_id"] = doc_id
    data["topic"] = query
    return data

def preview_context_query(doc_id: str, query: str, k: int = 8) -> dict:
    chunks = _semantic_chunks(doc_id, query, k=k)
    return {
        "docId": doc_id,
        "query": query,
        "k": k,
        "snippets": [c["text"] for c in chunks],
        "locations": [{"page": c["page"], "idx": c["idx"]} for c in chunks],
    }

# === Model setup: Qwen2.5 (open, no auth needed) ===
# You can also try: "Qwen/Qwen2.5-3B-Instruct" if you want a bit more quality.
MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
# Ensure padding token exists to avoid warnings on some environments
if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
    tokenizer.pad_token_id = tokenizer.eos_token_id

generate = pipeline(
    task="text-generation",
    model=MODEL_ID,
    tokenizer=tokenizer,
    device_map="auto",     # uses MPS on Apple Silicon, or CPU otherwise
    torch_dtype="auto"
)

# NOTE: all literal braces are doubled {{ }} so .format() only fills {context}
JSON_PROMPT = """You are an exam item writer. Output STRICT JSON only (no prose).
Schema:
{{
  "stem": "string",
  "options": ["A","B","C","D"],
  "answer": "A"
}}
Rules:
- Use exactly 4 options.
- Ensure the correct answer is one of the options.
- Use ONLY the provided Context; do not invent facts.
Context:
{context}
Return only the JSON object.
"""

def _strip_code_fences(text: str) -> str:
    t = text.strip()
    # common model wrappers: ```json ... ``` or ``` ...
    if t.startswith("```"):
        t = t.strip("`")
        # after stripping, model may leave 'json\n{...}'
        if t.lower().startswith("json"):
            t = t[4:].lstrip()
    return t

def _parse_json_safely(text: str) -> Dict[str, Any]:
    # clean code fences first
    text = _strip_code_fences(text)

    # extract the first {...} block from the (completion-only) text
    start, end = text.find("{"), text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except Exception:
            pass
    # Fallback if model returns unexpected format
    return {
        "stem": "Which organelle produces most ATP in eukaryotic cells?",
        "options": ["Ribosome", "Mitochondrion", "Golgi apparatus", "Lysosome"],
        "answer": "Mitochondrion",
    }

# --------------------------------------------------------------------------------------
# Qdrant-backed generation (uses chunks you stored via /ingest)
# --------------------------------------------------------------------------------------
import qdrant_client
from qdrant_client.models import Filter, FieldCondition, MatchValue

_QDRANT_COLLECTION = "notes"
_qdrant = qdrant_client.QdrantClient(host="127.0.0.1", port=6333)

def _get_doc_chunks(doc_id: str, k: int = 8) -> List[dict]:
    """Fetch up to k chunks for this doc_id (simple scroll; fast and dependency-light)."""
    flt = Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
    points, _ = _qdrant.scroll(
        collection_name=_QDRANT_COLLECTION,
        scroll_filter=flt,
        limit=k,
        with_payload=True,
    )
    return [
        {"text": p.payload["text"], "page": p.payload["page"], "idx": p.payload["idx"]}
        for p in points
        if p.payload and "text" in p.payload
    ]

async def generate_one_from_doc(doc_id: str, k: int = 8, max_tries: int = 3) -> Dict[str, Any]:
    """
    Retrieve up to k chunks for this doc from Qdrant, prompt Qwen with a grounded context,
    run quality gate, retry up to (max_tries) for better JSON. Returns dict or {"error": "..."}.
    """
    chunks = _get_doc_chunks(doc_id, k=k)
    if not chunks:
        return {"error": f"No chunks found for docId={doc_id}"}

    context = "\n".join([f"(p{c['page']}#{c['idx']}): {c['text']}" for c in chunks])

    last_item = None
    last_reason = ""
    for attempt in range(1, max_tries + 1):
        prompt = JSON_PROMPT.format(context=context)
        out = generate(
            prompt,
            max_new_tokens=260,
            do_sample=False,
            temperature=0.0,
            top_p=1.0
        )[0]["generated_text"]

        item = _normalize(_parse_json_safely(out))
        ok, why = _is_valid(item)
        if ok:
            item["source_doc_id"] = doc_id
            return item

        last_item, last_reason = item, why
        # Optional: slightly nudge with a follow-up corrective prompt on next loop
        # (kept simple here to avoid complexity)

    # If all tries failed, return an error (caller shouldn’t save it)
    return {
        "error": f"Failed quality checks after {max_tries} tries: {last_reason}",
        "last": last_item,
        "source_doc_id": doc_id,
    }

# --------------------------------------------------------------------------------------
# Existing simple (hardcoded-context) generator — unchanged except return_full_text
# --------------------------------------------------------------------------------------
async def generate_question() -> Dict[str, Any]:
    """
    Generate a single MCQ in strict JSON using Qwen2.5.
    Returns a dict with keys: stem, options, answer.
    """
    context = (
        "Mitochondria are double-membraned organelles that produce ATP via oxidative "
        "phosphorylation along the inner mitochondrial membrane (cristae)."
    )

    prompt = JSON_PROMPT.format(context=context)
    out = generate(
        prompt,
        max_new_tokens=200,
        do_sample=False,
        temperature=0.0,
        top_p=1.0,
        return_full_text=False,   # <-- IMPORTANT here too
    )[0]["generated_text"]

    return _parse_json_safely(out)

def get_preview_context(doc_id: str, k: int = 8) -> dict:
    chunks = _get_doc_chunks(doc_id, k=k)
    return {
        "docId": doc_id,
        "k": k,
        "snippets": [c["text"] for c in chunks],   # exact text fed to the model
        "locations": [{"page": c["page"], "idx": c["idx"]} for c in chunks],
    }

def _is_valid_item(d: Dict[str, Any]) -> bool:
    if not isinstance(d, dict): return False
    if "stem" not in d or "options" not in d or "answer" not in d: return False
    opts = d["options"]
    if not isinstance(opts, (list, tuple)) or len(opts) != 4: return False
    return d["answer"] in opts

_norm_ws = re.compile(r"\s+")
def _norm_stem(stem: str) -> str:
    # normalize to dedupe stems
    return _norm_ws.sub(" ", stem.strip().lower())

async def generate_batch_from_doc(
    doc_id: str,
    n: int,
    *,
    query: Optional[str] = None,
    k: int = 8,
    max_attempts_per_item: int = 3,
    sleep_between_calls: float = 0.0,  # set 0.2–0.5 if you ever hit rate limits
) -> list[Dict[str, Any]]:
    """
    Generate up to N unique MCQs (STRICT JSON) from a doc.
    - If `query` provided → semantic-focused retrieval
    - Otherwise → simple chunk scroll
    - Dedup by normalized stem
    - Retry a few times on bad/malformed outputs
    """
    results: list[Dict[str, Any]] = []
    seen: set[str] = set()

    for _ in range(n):
        attempt = 0
        item: Optional[Dict[str, Any]] = None

        while attempt < max_attempts_per_item:
            attempt += 1
            if query:
                d = await generate_from_doc_query(doc_id=doc_id, query=query, k=k)
            else:
                d = await generate_one_from_doc(doc_id=doc_id, k=k)

            if "error" in d:
                raise HTTPException(status_code=422, detail=item["error"])
                

            if _is_valid_item(d):
                key = _norm_stem(d["stem"])
                if key in seen:
                    print("[BATCH] duplicate stem detected; retrying…")
                else:
                    seen.add(key)
                    item = d
                    break
            else:
                print("[BATCH] invalid JSON shape or answer/options mismatch; retrying…")

            if sleep_between_calls:
                await asyncio.sleep(sleep_between_calls)

        if item:
            results.append(item)
        else:
            print("[BATCH] gave up on one item after retries")

    return results
