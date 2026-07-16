#main.py
import os
import psycopg
import httpx
import csv
from pathlib import Path
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()
PG_DSN = os.getenv('DATABASE_URL')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')
GROQ_GATE_MODEL = os.getenv('GROQ_GATE_MODEL', GROQ_MODEL)
DEBUG = os.getenv('DEBUG', 'false').lower() in ('1', 'true', 'yes')

def debug_print(msg: str):
    if DEBUG:
        print(msg)

if not GROQ_API_KEY:
    print("⚠️ GROQ_API_KEY not found. Please get one from console.groq.com")
    exit(1)

print("🔄 Loading embedding model...")
model = SentenceTransformer('BAAI/bge-m3', device='cpu')

# Load metadata from CSV files for document URL mapping
print("📂 Loading document metadata...")
metadata_lookup = {}

def load_metadata():
    """Load all metadata from CSV files to map filenames to URLs"""
    metadata_path = Path(__file__).parent / "scraper" / "metadata"
    csv_files = [
        "master_metadata.csv", 
        "cooperation_department_metadata.csv", 
        "gr_portal_metadata.csv", 
        "housing_department_metadata.csv", 
        "sahakarayukta_metadata.csv"
    ]
    
    for csv_file in csv_files:
        filepath = metadata_path / csv_file
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row and 'filename' in row:
                            filename = row.get('filename', '').strip()
                            if filename:
                                metadata_lookup[filename] = {
                                    'title': row.get('title', ''),
                                    'url': row.get('pdf_url', ''),
                                    'source_page': row.get('source_page', ''),
                                    'category': row.get('classified_category') or row.get('category', ''),
                                    'department': row.get('department', '')
                                }
            except Exception as e:
                if DEBUG:
                    print(f"⚠️ Error loading {csv_file}: {e}")
    
    print(f"✅ Loaded {len(metadata_lookup)} documents from metadata")

load_metadata()

# Single, consistent threshold used everywhere.
RELEVANCE_THRESHOLD = 0.28
# If embedding similarity is this confident, skip the LLM relevance gate entirely —
# the small/fast gate model can misjudge hypothetical or "what-if" phrasing
# ("can they skip the AGM?") as off-topic even when the match is obviously correct.
HIGH_CONFIDENCE_THRESHOLD = 0.45
TOP_K = 5
# How many chunks we average over to decide relevance (more stable than top-1 alone)
RELEVANCE_AVG_K = 3

conn = psycopg.connect(PG_DSN)

SYSTEM_PROMPT_TEMPLATE = """You explain Maharashtra Cooperative Housing Society laws and rules to
ordinary people, including people who have never read a legal document. You are NOT a search
engine reading out excerpts — you restate what the law says in plain, clear language.

Rules:
- Use simple, everyday words that anyone can understand, regardless of their education level.
  Avoid dense legal jargon. If a legal term is unavoidable (e.g. a section name), briefly explain
  what it means in plain language right after using it.
- Keep the tone plain, neutral, and clear — like a helpful public information desk. Do NOT use
  casual or friendly chit-chat language; do not address the user like a friend. Stay respectful
  and matter-of-fact, simply easy to follow.
- Do NOT cite bracket references like [1] or [2] in your reply. If relevant, you may mention
  in passing which act or circular something comes from, in plain wording.
- Each user message will explicitly state which language to answer in. Follow that instruction
  exactly, even if the document text given to you is in a different language than the answer
  should be in. Translate/restate the substance — never mirror the language of the source text.
- Base your answer only on the information given to you. If it does not actually answer the
  question, say so plainly in ONE short sentence and STOP THERE — do not follow it with a
  general-knowledge explanation anyway. Never answer from knowledge outside the provided
  information, even if you personally know the answer. A partial or incomplete answer drawn
  ONLY from the given information is fine and preferred over a complete answer drawn from
  outside knowledge.
- Never use a hedge-then-answer pattern such as "the information doesn't say X, however in
  general X means..." or "this isn't explicitly stated, but typically...". Either the provided
  information answers the question (answer directly) or it doesn't (say so briefly and stop).
- Never explain a concept in general terms and then re-explain the same concept "in the context
  of housing societies" as a second pass. Write one merged explanation, once.
- Give ONE direct, coherent answer. Never restate the same point twice in different words across
  separate paragraphs. Keep answers as short as the question needs; a simple question deserves a
  few sentences, not multiple paragraphs saying the same thing.
- Keep continuity with the earlier conversation where relevant.
"""

REFUSAL_MARATHI = (
    "मी फक्त महाराष्ट्र सहकारी गृहनिर्माण संस्था कायदे आणि नियमांबद्दल बोलू शकतो. "
    "कृपया या विषयाशी संबंधित प्रश्न विचारा."
)
REFUSAL_ENGLISH = (
    "I can only help with questions about Maharashtra Cooperative Housing Society laws and rules. "
    "Could you ask something related to that?"
)

# Small allow-list of standard acronyms used constantly in housing-society contexts.
# These get injected as a fixed factual note in the prompt so the model doesn't have
# to guess, hedge, or fall back on outside knowledge to expand them.
KNOWN_ACRONYMS = {
    "agm": "AGM = Annual General Meeting (वार्षिक सर्वसाधारण सभा) — the yearly meeting of all society members.",
    "sgm": "SGM = Special General Meeting (विशेष सर्वसाधारण सभा) — a general meeting called for a specific urgent matter, outside the annual one.",
    "egm": "EGM = Extraordinary General Meeting (असाधारण सर्वसाधारण सभा) — a general meeting called for a specific urgent matter, outside the annual one.",
    "gbm": "GBM = General Body Meeting (सर्वसाधारण सभा) — a meeting of all members of the society.",
    "mc": "MC = Managing Committee (व्यवस्थापन समिती) — the elected body that runs the day-to-day affairs of the society.",
    "noc": "NOC = No Objection Certificate (ना हरकत प्रमाणपत्र) — a document stating the society has no objection to something (e.g. a transfer or construction).",
    "mcs act": "MCS Act = Maharashtra Cooperative Societies Act, 1960 — the main law governing cooperative societies in Maharashtra.",
    "byelaws": "Bye-laws = the specific internal rules of an individual society, made under the model bye-laws framework.",
}


def embed(text: str):
    return model.encode(text, normalize_embeddings=True).tolist()


def retrieve(query_vector):
    """Single query: fetch top-K chunks with similarity, used for BOTH the relevance
    check and the actual context. No second round-trip, no mismatched thresholds."""
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
            LIMIT %s;
        """, (query_vector, query_vector, TOP_K))
        return cur.fetchall()


def retrieve_merged(vectors):
    """Run retrieval for multiple query vectors and merge the results.

    Used so that if the Marathi translation of an English query is slightly off
    (e.g. an awkward or overly literal phrasing), we still have a second shot via
    the original English query's own embedding. Rows are deduped by content and
    the best (highest-similarity) score for each chunk is kept.
    """
    best = {}
    for vec in vectors:
        for content, page, filename, sim in retrieve(vec):
            key = (filename, page, content)
            if key not in best or sim > best[key][3]:
                best[key] = (content, page, filename, sim)
    merged = sorted(best.values(), key=lambda r: r[3], reverse=True)
    return merged[:TOP_K]


def compute_avg_similarity(rows) -> float:
    if not rows:
        return 0.0
    top = [r[3] for r in rows[:RELEVANCE_AVG_K]]
    return sum(top) / len(top)


def is_relevant(rows) -> bool:
    if not rows:
        debug_print("   [debug] no rows retrieved from DB")
        return False
    avg_top = compute_avg_similarity(rows)
    debug_print(f"   [debug] top-{RELEVANCE_AVG_K} avg similarity = {avg_top:.3f} (threshold {RELEVANCE_THRESHOLD})")
    return avg_top >= RELEVANCE_THRESHOLD


def looks_marathi(text: str) -> bool:
    """Check if text contains Marathi (Devanagari script)"""
    return any('\u0900' <= c <= '\u097F' for c in text)


def detect_language_and_script(text: str) -> tuple:
    """Detect language and return (is_devanagari, language_name, language_code)
    
    Returns:
        (is_devanagari: bool, language_name: str, language_code: str)
        - is_devanagari: True if using Devanagari script (Marathi in native script)
        - language_name: Display name for the language
        - language_code: Code for the language (marathi_native, english)
    """
    if looks_marathi(text):
        return True, "Marathi (Devanagari)", "marathi_native"
    else:
        return False, "English", "english"


def translate_to_marathi(text: str) -> str:
    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": GROQ_GATE_MODEL,  # small/fast model, this is a cheap utility call
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Translate the following question into MARATHI (not Hindi — Marathi "
                            "and Hindi share the Devanagari script but are different languages "
                            "with different words; e.g. use 'काय' not 'क्या', use 'आहे' not 'है'). "
                            "Keep any legal/technical terms accurate. Output ONLY the Marathi "
                            "translation, nothing else — no quotes, no explanation.\n\n"
                            f"Question: {text}"
                        ),
                    }
                ],
                "temperature": 0,
                "max_tokens": 200,
            },
            timeout=20,
        )
        response.raise_for_status()
        translated = response.json()["choices"][0]["message"]["content"].strip()
        debug_print(f"   [debug] translated query for retrieval: {translated!r}")
        return translated if translated else text
    except Exception as e:
        debug_print(f"   ⚠️ [debug] translation call failed, falling back to original query: {e}")
        return text


def find_known_acronyms(query: str):
    """Return plain-language expansions for any known acronyms mentioned in the query.
    Injected into the prompt as a fixed fact so the model doesn't have to hedge or
    invent an expansion from outside knowledge."""
    q = query.lower()
    hits = []
    for key, note in KNOWN_ACRONYMS.items():
        # word-boundary-ish check so "mc" doesn't match inside "much"
        # Also check for "what is AGM" or similar patterns
        found = (
            f" {key} " in f" {q} " or
            f" {key}?" in q or
            f" {key}." in q or
            f" {key}," in q or
            q.endswith(f"{key}?") or
            q.endswith(f"{key}.") or
            q.strip() == key or
            q.startswith(key + " ") or
            q.endswith(" " + key) or
            f"is {key} " in q or
            f"what {key}" in q or
            f"about {key}" in q
        )
        if found and note not in hits:
            hits.append(note)
    return hits


def is_topically_relevant_llm(query: str, rows) -> bool:
    """Second guardrail, run AFTER the embedding pre-filter passes.

    Embedding similarity alone isn't reliable here: with an all-Marathi knowledge
    base, any generic Marathi sentence can score deceptively high against Marathi
    legal text simply because they share a language, not a topic. This asks the
    model directly, using the actual question, whether it's really on-topic.
    Uses a small/fast model and a tiny max_tokens since we only need YES/NO.
    """
    preview = "\n".join(f"- {r[0][:400]}" for r in rows[:3])
    check_prompt = (
        "Question: " + query + "\n\n"
        "Document snippets retrieved from a Maharashtra Cooperative Housing Society "
        "law knowledge base for this question:\n"
        + preview + "\n\n"
        "The question may be short or use an acronym (e.g. AGM = Annual General Meeting) "
        "that only makes sense once you look at the snippets above.\n\n"
        "Answer NO only if the question is clearly about something unrelated to housing "
        "societies altogether (e.g. weather, sports, movies, general trivia). "
        "If the snippets above plausibly answer the question, or the question could "
        "reasonably be about housing society administration, answer YES.\n\n"
        "Reply with exactly one word: YES or NO."
    )
    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": GROQ_GATE_MODEL,  # fast/cheap model just for this gate
                "messages": [{"role": "user", "content": check_prompt}],
                "temperature": 0,
                "max_tokens": 5,
            },
            timeout=20,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip().upper()
        debug_print(f"   [debug] relevance gate model={GROQ_GATE_MODEL} raw_answer={answer!r}")
        return answer.startswith("Y")
    except Exception as e:
        # Fail-safe (blocks the question), but SHOW why instead of hiding it.
        debug_print(f"   ⚠️ [debug] relevance gate call failed: {e}")
        return False


def build_context(rows):
    parts, sources = [], []
    for i, (content, page, filename, sim) in enumerate(rows, 1):
        if sim < RELEVANCE_THRESHOLD:
            continue  # drop weak chunks even if a few strong ones passed
        parts.append(f"[{i}] {content}")
        
        # Get metadata for this file if available
        meta = metadata_lookup.get(filename, {})
        url = meta.get('url', '')
        title = meta.get('title', filename)
        
        # Format source with URL if available
        if url:
            source_text = f"{title} (पृष्ठ {page}) - {url}"
        else:
            source_text = f"{filename} (पृष्ठ {page})"
        
        sources.append(source_text)
    
    return "\n\n".join(parts), sources


def call_groq(history):
    response = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": GROQ_MODEL,
            "messages": history,
            "temperature": 0.4,
            "max_tokens": 1024,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def main():
    print("🏠 नमस्कार! Housing Society संदर्भात विचारा (type 'exit' to quit)\n")

    # Conversation memory — this is what makes follow-up questions feel human.
    conversation = [{"role": "system", "content": SYSTEM_PROMPT_TEMPLATE}]

    while True:
        query = input("❓ तुमचा प्रश्न: ").strip()
        if not query:
            continue  # blank Enter — just re-prompt, don't treat as exit
        if query.lower() in ("exit", "quit"):
            print("धन्यवाद! 🙏")
            break

        # Detect user's language and script (preserves original input language)
        is_devanagari, lang_display, lang_code = detect_language_and_script(query)
        
        # For retrieval, use Marathi (the knowledge base is all Marathi)
        # If query is in English, translate to Marathi for retrieval
        if is_devanagari:
            rows = retrieve_merged([embed(query)])
        else:
            retrieval_query = translate_to_marathi(query)
            rows = retrieve_merged([embed(retrieval_query), embed(query)])

        # Stage 1: cheap embedding pre-filter — cuts off obviously unrelated queries
        # without spending an LLM call.
        if not is_relevant(rows):
            refusal = REFUSAL_MARATHI if is_devanagari else REFUSAL_ENGLISH
            print(f"\n{refusal}\n")
            continue

        # Stage 2: LLM-based relevance gate — catches cases where embedding
        # similarity is misleading (e.g. a generic sentence in the same language
        # as the knowledge base scoring high despite being off-topic). Skipped
        # when Stage 1 similarity is already high-confidence, since the small/fast
        # gate model can misjudge hypothetical or "what-if" phrasing as off-topic
        # even when the topical match is clearly correct.
        avg_similarity = compute_avg_similarity(rows)
        if avg_similarity < HIGH_CONFIDENCE_THRESHOLD:
            if not is_topically_relevant_llm(query, rows):
                refusal = REFUSAL_MARATHI if is_devanagari else REFUSAL_ENGLISH
                print(f"\n{refusal}\n")
                continue
        else:
            debug_print(f"   [debug] skipping LLM relevance gate — high-confidence similarity ({avg_similarity:.3f} >= {HIGH_CONFIDENCE_THRESHOLD})")

        context, sources = build_context(rows)
        if not context:
            refusal = REFUSAL_MARATHI if is_devanagari else REFUSAL_ENGLISH
            print(f"\n{refusal}\n")
            continue

        acronym_notes = find_known_acronyms(query)
        acronym_block = ""
        if acronym_notes:
            acronym_block = (
                "\n\nKnown acronym expansions (treat these as established fact, "
                "do not hedge about them):\n" + "\n".join(f"- {n}" for n in acronym_notes)
            )

        # Build language directive based on user's original input language
        if is_devanagari:
            language_directive = "Marathi (Devanagari script - NOT romanized, use native Devanagari characters)"
        else:
            language_directive = "English"
        
        user_turn = (
            f"Relevant information:\n{context}"
            f"{acronym_block}\n\n"
            f"Question: {query}\n\n"
            f"(Answer strictly in {language_directive}, regardless of what language the "
            f"information above is written in. DO NOT use romanized spelling if the user asked in Devanagari.)"
        )
        conversation.append({"role": "user", "content": user_turn})

        try:
            answer = call_groq(conversation)
            conversation.append({"role": "assistant", "content": answer})

            print("\n" + "=" * 60)
            print(answer)
            if sources:
                print("\n📚 संदर्भ / References:")
                for source in sorted(set(sources)):
                    print(f"  • {source}")
            print("=" * 60 + "\n")
        except Exception as e:
            print(f"❌ Error: {e}\n")
            conversation.pop()  # don't keep a failed turn in memory


if __name__ == "__main__":
    try:
        main()
    finally:
        conn.close()