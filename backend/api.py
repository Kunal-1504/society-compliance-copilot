#!/usr/bin/env python3
"""
Society Compliance Copilot — FastAPI backend
==============================================
This file powers the React frontend. It uses the SAME pgvector RAG pipeline
as main.py (vector search, translation, relevance gates, grounded prompts).

Pipeline per request:
  1. Language detection (Devanagari / Romanized Marathi / English)
  2. Query expansion (acronyms → full forms)
  3. Hard keyword off-topic filter (instant reject, no LLM)
  4. Translation to Marathi for retrieval (if query is English/Romanized)
  5. Vector similarity search via pgvector (top-K chunks)
  6. Embedding-based relevance gate (avg cosine similarity threshold)
  7. LLM relevance gate (for borderline cases below high-confidence threshold)
  8. Context building from retrieved chunks
  9. Grounded LLM answer generation (answers ONLY from retrieved text)
 10. Source URL enrichment from metadata CSV
"""
import os
import re
import csv
import logging
import httpx
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from pathlib import Path
from sentence_transformers import SentenceTransformer

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("api")

# ── Configuration ──────────────────────────────────────────────────────────────
PG_DSN          = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/mahacoop_rag")
GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL      = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_GATE_MODEL = os.getenv("GROQ_GATE_MODEL", "llama3-8b-8192")
DEBUG           = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")

# Retrieval tuning
TOP_K                  = 8      # retrieve more chunks → better recall
RELEVANCE_THRESHOLD    = 0.25   # min cosine similarity to keep a chunk
HIGH_CONF_THRESHOLD    = 0.42   # skip LLM gate when embedding score is already this high
RELEVANCE_AVG_K        = 3      # average over top-N chunks for the similarity check

# ── Embedding model ────────────────────────────────────────────────────────────
logger.info("Loading embedding model BAAI/bge-m3 ...")
_embed_model = SentenceTransformer("BAAI/bge-m3", device="cpu")
logger.info("Embedding model ready.")

def embed(text: str) -> list:
    return _embed_model.encode(text, normalize_embeddings=True).tolist()

# ── Postgres connection (pgvector) ─────────────────────────────────────────────
_conn: Optional[psycopg.Connection] = None

def get_conn() -> Optional[psycopg.Connection]:
    global _conn
    try:
        if _conn is None or _conn.closed:
            _conn = psycopg.connect(PG_DSN)
            logger.info("Connected to PostgreSQL/pgvector.")
        return _conn
    except Exception as e:
        logger.warning(f"DB connection failed: {e}. Will use keyword fallback.")
        return None

# Try to connect at startup (non-fatal if DB is not yet available)
get_conn()

# ── Metadata CSV lookup ────────────────────────────────────────────────────────
logger.info("Loading document metadata from CSV files ...")
metadata_lookup: Dict[str, Dict] = {}

def load_metadata():
    meta_path = Path(__file__).parent / "scraper" / "metadata"
    csv_files = [
        "master_metadata.csv",
        "cooperation_department_metadata.csv",
        "gr_portal_metadata.csv",
        "housing_department_metadata.csv",
        "sahakarayukta_metadata.csv",
    ]
    for fname in csv_files:
        fpath = meta_path / fname
        if not fpath.exists():
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    filename = (row.get("filename") or "").strip()
                    if filename:
                        metadata_lookup[filename] = {
                            "title":       row.get("title", ""),
                            "url":         row.get("pdf_url", ""),
                            "source_page": row.get("source_page", ""),
                            "category":    row.get("classified_category") or row.get("category", ""),
                            "department":  row.get("department", ""),
                        }
        except Exception as e:
            logger.warning(f"Error loading {fname}: {e}")
    logger.info(f"Loaded {len(metadata_lookup)} documents from metadata.")

load_metadata()

# ── Known acronyms ─────────────────────────────────────────────────────────────
KNOWN_ACRONYMS = {
    "agm":      "AGM = Annual General Meeting (वार्षिक सर्वसाधारण सभा) — the yearly meeting of all society members.",
    "sgm":      "SGM = Special General Meeting (विशेष सर्वसाधारण सभा) — a general meeting called for a specific urgent matter.",
    "egm":      "EGM = Extraordinary General Meeting (असाधारण सर्वसाधारण सभा) — an urgent meeting outside the annual one.",
    "gbm":      "GBM = General Body Meeting (सर्वसाधारण सभा) — a meeting of all members of the society.",
    "mc":       "MC = Managing Committee (व्यवस्थापन समिती) — the elected body that runs the day-to-day affairs of the society.",
    "noc":      "NOC = No Objection Certificate (ना हरकत प्रमाणपत्र) — a certificate stating the society has no objection.",
    "mcs act":  "MCS Act = Maharashtra Cooperative Societies Act, 1960 — the main law governing cooperative societies in Maharashtra.",
    "mcs":      "MCS = Maharashtra Cooperative Societies Act, 1960.",
    "byelaws":  "Bye-laws = the specific internal rules of an individual society.",
    "dc":       "DC = Deemed Conveyance — the legal transfer of land title to the society when the builder has not done so.",
}

# ── Off-topic keyword blocklist ────────────────────────────────────────────────
OFF_TOPIC_KEYWORDS = [
    "ipl","cricket","football","soccer","fifa","nba","nfl","tennis",
    "tournament","world cup","olympics","sports",
    "movie","film","actor","actress","bollywood","netflix","web series",
    "game","gaming","pubg","fortnite","valorant",
    "weather","temperature","forecast","rainfall",
    "war","army","missile","nuclear",
    "stock market","share price","crypto","bitcoin","nifty","sensex",
    "recipe","cooking","food","restaurant","chef",
    "celebrity","singer","singer","music album","concert",
    "religion","god","temple","mosque","church",
    "ganesha","ganesh","durga","shiva","vishnu","allah","jesus",
    "exam","school","college","university","jee","neet","upsc",
]
# A question with an off-topic keyword is still allowed if it ALSO mentions
# housing society context.
SOCIETY_SAFE_KEYWORDS = [
    "society","cooperative","housing","flat","member","committee",
    "agm","sgm","egm","gbm","noc","bye-law","byelaw","maintenance",
    "redevelopment","mcs","maharashtra","secretary","chairman","treasurer",
    "sinking fund","repair fund","audit","share certificate","managing",
    "tenant","landlord","lease","transfer","registration","conveyance",
]

# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(title="Society Compliance Copilot API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ── Pydantic models ────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str
    top_k: Optional[int] = TOP_K

class QueryResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    language: Optional[str] = None
    debug: Optional[Dict[str, Any]] = None

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You explain Maharashtra Cooperative Housing Society laws and rules to
ordinary people, including people who have never read a legal document. You are NOT a search
engine reading out excerpts — you restate what the law says in plain, clear language.

Rules:
- Use simple, everyday words. Avoid dense legal jargon; if unavoidable, explain it inline.
- Keep the tone plain, neutral, and clear — like a helpful public information desk.
- Do NOT cite bracket references like [1] or [2] in your reply.
- Each user message will explicitly state which language to answer in. Follow that instruction exactly.
- Base your answer ONLY on the information provided to you. If it does not actually answer
  the question, say so in ONE short sentence and STOP — do not add a general-knowledge answer.
- Never use a hedge-then-answer pattern like "the information doesn't say X, however in general..."
- Give ONE direct, coherent answer. Never restate the same point twice.
"""

REFUSAL_EN = "I can only help you with questions about Maharashtra Cooperative Housing Society laws and rules. Could you ask something related to that?"
REFUSAL_MR = "मी फक्त महाराष्ट्र सहकारी गृहनिर्माण संस्था कायदे आणि नियमांबद्दल बोलू शकतो. कृपया या विषयाशी संबंधित प्रश्न विचारा."

# ══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ══════════════════════════════════════════════════════════════════════════════

def detect_language(text: str) -> tuple:
    """Returns (lang_code, display_name, is_devanagari)."""
    deva_ratio = sum(1 for c in text if 0x0900 <= ord(c) <= 0x097F) / max(len(text), 1)
    if deva_ratio > 0.25:
        return "marathi_native", "मराठी", True

    romanized_pattern = r"\b(aai|aapla|aaplya|tumhi|kasa|kashi|kiti|kon|kuthe|kadhi|karu|sathi|samjha|mhatla|mazi|mahiti|gheu|kela|ahe|aahe|nahi|sang|mhanje|tasa|ghya|khup|karya|kay|tar|pan|aani|ani|kaaran|madhe|hota|lagte|adhyaksha|sachiv|koshadhyaksha|charcha|nivadnuk|sabhasad|karyakari|mandal)\b"
    if re.search(romanized_pattern, text, re.IGNORECASE):
        return "romanized_marathi", "Romanized Marathi", False

    return "english", "English", False


def find_acronyms(query: str) -> List[str]:
    """Return plain-language expansions for acronyms in the query."""
    q = query.lower()
    hits = []
    for key, note in KNOWN_ACRONYMS.items():
        if (f" {key} " in f" {q} " or f" {key}?" in q or f" {key}." in q
                or q.strip() == key or q.startswith(key + " ") or q.endswith(" " + key)
                or f"is {key} " in q or f"what {key}" in q):
            if note not in hits:
                hits.append(note)
    return hits


def is_off_topic(query: str) -> bool:
    """Quick keyword pre-filter — no LLM call needed."""
    q = query.lower()
    has_off_topic = any(kw in q for kw in OFF_TOPIC_KEYWORDS)
    has_society   = any(kw in q for kw in SOCIETY_SAFE_KEYWORDS)
    return has_off_topic and not has_society


def translate_to_marathi(text: str) -> str:
    """Translate English / Romanized Marathi to Devanagari for retrieval."""
    try:
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": GROQ_GATE_MODEL,
                "messages": [{
                    "role": "user",
                    "content": (
                        "Translate the following question into MARATHI (Devanagari script). "
                        "Use Marathi words, NOT Hindi (e.g. 'काय' not 'क्या', 'आहे' not 'है'). "
                        "Keep legal and technical terms accurate. Output ONLY the Marathi translation, "
                        "nothing else — no quotes, no explanation.\n\nQuestion: " + text
                    ),
                }],
                "temperature": 0,
                "max_tokens": 200,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        translated = resp.json()["choices"][0]["message"]["content"].strip()
        if DEBUG: logger.info(f"Translated query: {translated!r}")
        return translated or text
    except Exception as e:
        logger.warning(f"Translation failed, using original: {e}")
        return text


# ── Vector retrieval ───────────────────────────────────────────────────────────

def vector_retrieve(query_vec: list, top_k: int) -> list:
    """Retrieve top-K chunks from pgvector ordered by cosine similarity."""
    conn = get_conn()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    dc.content,
                    dc.source_page_start,
                    d.file_name,
                    1 - (dc.embedding <=> %s::vector) AS similarity
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                ORDER BY dc.embedding <=> %s::vector
                LIMIT %s
            """, (query_vec, query_vec, top_k))
            return cur.fetchall()
    except Exception as e:
        logger.warning(f"Vector search failed: {e}")
        # Reset connection so the next call retries
        global _conn
        _conn = None
        return []


def retrieve_merged(vectors: list, top_k: int) -> list:
    """Run retrieval for multiple query vectors and merge by best score."""
    best = {}
    for vec in vectors:
        for content, page, filename, sim in vector_retrieve(vec, top_k):
            key = (filename, page, content[:80])
            if key not in best or sim > best[key][3]:
                best[key] = (content, page, filename, sim)
    merged = sorted(best.values(), key=lambda r: r[3], reverse=True)
    return merged[:top_k]


def avg_similarity(rows: list) -> float:
    if not rows:
        return 0.0
    top = [r[3] for r in rows[:RELEVANCE_AVG_K]]
    return sum(top) / len(top)


def is_embedding_relevant(rows: list) -> bool:
    score = avg_similarity(rows)
    if DEBUG: logger.info(f"Avg similarity (top-{RELEVANCE_AVG_K}): {score:.3f} (threshold {RELEVANCE_THRESHOLD})")
    return score >= RELEVANCE_THRESHOLD


def llm_relevance_gate(query: str, rows: list) -> bool:
    """Ask a small/fast LLM whether the retrieved chunks actually match the query."""
    preview = "\n".join(f"- {r[0][:350]}" for r in rows[:3])
    prompt = (
        f"Question: {query}\n\n"
        "Document snippets from a Maharashtra Cooperative Housing Society knowledge base:\n"
        f"{preview}\n\n"
        "The question may be short or use an acronym (e.g. AGM = Annual General Meeting). "
        "Answer NO only if the question is CLEARLY about something unrelated to housing societies "
        "(e.g. weather, sports, movies, general trivia). "
        "If the snippets plausibly answer the question or the question is about housing/property, answer YES.\n\n"
        "Reply with exactly one word: YES or NO."
    )
    try:
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": GROQ_GATE_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0, "max_tokens": 5,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip().upper()
        if DEBUG: logger.info(f"LLM relevance gate answer: {answer!r}")
        return answer.startswith("Y")
    except Exception as e:
        logger.warning(f"LLM relevance gate failed: {e}")
        return True  # fail open — let the answer stage decide


def build_context(rows: list) -> tuple:
    """Build LLM context string and source list from retrieved chunks."""
    parts, sources = [], []
    for i, (content, page, filename, sim) in enumerate(rows, 1):
        if sim < RELEVANCE_THRESHOLD:
            continue
        parts.append(f"[Chunk {i} | {filename} p.{page} | score {sim:.2f}]\n{content}")
        meta = metadata_lookup.get(filename, {})
        sources.append({
            "filename":    filename,
            "title":       meta.get("title") or filename,
            "url":         meta.get("url", ""),
            "source_page": meta.get("source_page", ""),
            "category":    meta.get("category", ""),
            "department":  meta.get("department", ""),
            "page":        page,
            "similarity":  round(sim, 3),
        })
    return "\n\n".join(parts), sources


# ── Keyword fallback (when pgvector is unreachable) ────────────────────────────

def keyword_search(query: str, top_k: int) -> list:
    """Simple filename-based keyword search as a fallback when DB is unavailable."""
    dataset_path = Path(__file__).parent / "scraper" / "dataset"
    documents = []
    if dataset_path.exists():
        for cat_dir in dataset_path.iterdir():
            if cat_dir.is_dir():
                for pdf in cat_dir.glob("*.pdf"):
                    meta = metadata_lookup.get(pdf.name, {})
                    documents.append({
                        "filename": pdf.name,
                        "category": cat_dir.name,
                        "title":    meta.get("title", pdf.name),
                        "url":      meta.get("url", ""),
                        "source_page": meta.get("source_page", ""),
                        "department":  meta.get("department", ""),
                    })

    query_words = set(query.lower().split())
    scored = []
    for doc in documents[:100]:
        doc_words = set(doc["filename"].lower().replace(".pdf","").replace("_"," ").split())
        score = len(query_words & doc_words) / max(len(query_words), 1)
        if doc.get("category") and any(w in doc["category"].lower() for w in query_words):
            score += 0.3
        if score > 0:
            scored.append((doc, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [d for d, _ in scored[:top_k]]


# ── LLM answer generation ──────────────────────────────────────────────────────

def generate_answer(query: str, context: str, language_directive: str,
                    acronym_notes: list) -> str:
    acronym_block = ""
    if acronym_notes:
        acronym_block = (
            "\n\nKnown acronym expansions (treat as established fact):\n"
            + "\n".join(f"- {n}" for n in acronym_notes)
        )

    user_turn = (
        f"Relevant information from indexed government documents:\n{context}"
        f"{acronym_block}\n\n"
        f"Question: {query}\n\n"
        f"(Answer strictly in {language_directive}.)"
    )

    try:
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_turn},
                ],
                "temperature": 0.3,
                "max_tokens": 1024,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Groq answer generation failed: {e}")
        return "I'm sorry, I encountered an error generating an answer. Please try again."


# ══════════════════════════════════════════════════════════════════════════════
# API Endpoints
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"message": "Society Compliance Copilot API v2.0", "status": "running"}


@app.get("/health")
async def health():
    conn = get_conn()
    db_ok = False
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            db_ok = True
        except Exception:
            pass
    return {
        "status": "healthy",
        "database": "connected" if db_ok else "unavailable (keyword fallback active)",
        "groq_api": "configured" if GROQ_API_KEY else "missing",
        "embedding_model": "BAAI/bge-m3",
    }


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """Main RAG query endpoint."""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    top_k = request.top_k or TOP_K
    debug_info: Dict[str, Any] = {}

    try:
        # ── Step 1: Language detection ─────────────────────────────────────────
        lang_code, lang_display, is_devanagari = detect_language(query)
        debug_info["language"] = lang_display
        if DEBUG: logger.info(f"Query language: {lang_display} | query: {query!r}")

        # ── Step 2: Hard off-topic keyword filter ──────────────────────────────
        if is_off_topic(query):
            refusal = REFUSAL_MR if is_devanagari else REFUSAL_EN
            return QueryResponse(answer=refusal, sources=[], confidence=0.0,
                                 language=lang_display)

        # ── Step 3: Acronym expansion ──────────────────────────────────────────
        acronym_notes = find_acronyms(query)
        debug_info["acronyms"] = acronym_notes

        # ── Step 4: Retrieval ──────────────────────────────────────────────────
        conn = get_conn()
        db_available = conn is not None

        if db_available:
            # Build retrieval vectors: translate non-Marathi queries for better recall
            if is_devanagari:
                vectors = [embed(query)]
            else:
                marathi_query = translate_to_marathi(query)
                debug_info["marathi_query"] = marathi_query
                vectors = [embed(marathi_query), embed(query)]

            rows = retrieve_merged(vectors, top_k)
            
            # If vector retrieval completely failed (e.g., table doesn't exist), fall back to keyword
            if not rows:
                logger.warning("Vector retrieval returned no rows, falling back to keyword search.")
                db_available = False

        if db_available and rows:
            debug_info["retrieved_chunks"] = len(rows)
            debug_info["top_similarity"] = round(rows[0][3], 3) if rows else 0.0

            # ── Step 5: Embedding relevance gate ──────────────────────────────
            if not is_embedding_relevant(rows):
                refusal = REFUSAL_MR if is_devanagari else REFUSAL_EN
                return QueryResponse(answer=refusal, sources=[], confidence=0.0,
                                     language=lang_display)

            # ── Step 6: LLM relevance gate (skip when already high-confidence) ─
            avg_sim = avg_similarity(rows)
            if avg_sim < HIGH_CONF_THRESHOLD:
                if not llm_relevance_gate(query, rows):
                    refusal = REFUSAL_MR if is_devanagari else REFUSAL_EN
                    return QueryResponse(answer=refusal, sources=[], confidence=0.0,
                                         language=lang_display)
            else:
                if DEBUG: logger.info(f"Skipping LLM gate — high similarity {avg_sim:.3f}")

            context, sources = build_context(rows)
            if not context:
                refusal = REFUSAL_MR if is_devanagari else REFUSAL_EN
                return QueryResponse(answer=refusal, sources=[], confidence=0.0,
                                     language=lang_display)
            confidence = min(avg_sim, 0.99)

        if not db_available:
            # ── Fallback: keyword search ────────────────────────────────────────
            logger.warning("Using keyword search fallback (DB unavailable or empty)")
            docs = keyword_search(query, top_k)
            if not docs:
                return QueryResponse(
                    answer="I couldn't find relevant information in the indexed government documents.",
                    sources=[], confidence=0.0, language=lang_display,
                )
            context = "\n\n".join(
                f"[Document: {d['filename']} | Category: {d['category']}]" for d in docs
            )
            sources = docs
            confidence = 0.4
            debug_info["mode"] = "keyword_fallback"

        # ── Step 7: Build language directive ──────────────────────────────────
        if is_devanagari:
            language_directive = "Marathi using Devanagari script (NOT romanized)"
        elif lang_code == "romanized_marathi":
            language_directive = "Romanized Marathi (Latin script, phonetic Marathi spelling)"
        else:
            language_directive = "English"

        # ── Step 8: Generate grounded answer ──────────────────────────────────
        answer = generate_answer(query, context, language_directive, acronym_notes)

        # ── Step 9: Enrich sources with domain info ────────────────────────────
        enriched_sources = []
        seen = set()
        for s in sources:
            url = s.get("url", "") or s.get("source_page", "")
            key = s.get("filename", url)
            if key in seen:
                continue
            seen.add(key)
            domain = ""
            if url:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).hostname or ""
                except Exception:
                    pass
            enriched_sources.append({
                "title":       s.get("title", s.get("filename", "Unknown")),
                "filename":    s.get("filename", ""),
                "url":         url,
                "source_page": s.get("source_page", ""),
                "category":    s.get("category", ""),
                "department":  s.get("department", ""),
                "domain":      domain,
                "page":        s.get("page", ""),
                "similarity":  s.get("similarity", 0),
            })

        return QueryResponse(
            answer=answer,
            sources=enriched_sources,
            confidence=round(confidence, 3),
            language=lang_display,
            debug=debug_info if DEBUG else None,
        )

    except Exception as e:
        logger.exception(f"Unhandled error in /query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
async def list_documents():
    """List all available documents from metadata."""
    docs = [
        {"filename": fname, **meta}
        for fname, meta in list(metadata_lookup.items())[:100]
    ]
    return {"total": len(metadata_lookup), "documents": docs}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
