#vector_store.py

"""
app/services/vector_store.py

Async ingestion + retrieval backbone for the MahaCoOp RAG pipeline.

Pipeline stages inside process_and_index_pdf():
    1. PyMuPDF native text extraction, with Tesseract OCR (via pytesseract on a
       rendered page image) as the fallback for scanned/low-text pages.
    2. Pages still with < OCR_MIN_CHARS chars fall back to Gemini Vision API
       (DISABLED BY DEFAULT right now via DISABLE_GEMINI_VISION — see below).
    3. Gemini 2.5 Flash text cleanup is SKIPPED by default while rate-limited;
       raw extracted text is lightly whitespace-normalized instead.
    4. Hybrid structure-aware + recursive chunking (600 chars / 60 overlap).
    5. BAAI/bge-m3 dense embeddings via sentence-transformers.
    6. Bulk write to Postgres (documents + document_chunks) via psycopg3
       async connection pool, with pgvector's vector type registered.

=== IMPORTANT FLAGS (top of file) ===
DISABLE_GEMINI_VISION = True   -> flip to False once your Gemini quota resets
SKIP_GEMINI_CLEANUP   = True   -> flip to False once your Gemini quota resets
TESSERACT_LANG        = "eng+mar" -> Marathi uses 'mar' tessdata, NOT 'hin'.
    Make sure `tesseract-ocr-mar` is installed (you already have it) and that
    `tesseract --list-langs` shows 'mar' in the list.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx
import pdfplumber
import pymupdf
import pytesseract
import torch
from dotenv import load_dotenv
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from pgvector.psycopg import register_vector_async
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from sentence_transformers import SentenceTransformer
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from PIL import Image

# Fix for NumPy 2.0 compatibility
import numpy as np
if not hasattr(np, "sctypes"):
    np.sctypes = {
        "float": [np.float16, np.float32, np.float64],
        "int": [np.int8, np.int16, np.int32, np.int64],
        "uint": [np.uint8, np.uint16, np.uint32, np.uint64],
        "others": [bool, complex, object, str, bytes]
    }
if not hasattr(np, "long"): np.long = int

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vector_store")

# ============================================================
# Config
# ============================================================
_DEFAULT_DATABASE_URL = "postgresql://postgres:secretpassword@127.0.0.1:5432/mahasociety_rag"
PG_DSN = os.getenv("DATABASE_URL") or _DEFAULT_DATABASE_URL

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", 1024))

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 600))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 60))

OCR_MIN_CHARS = 100
OCR_DPI = 350  # higher DPI helps small Devanagari glyphs
TESSERACT_LANG = os.getenv("TESSERACT_LANG", "eng+mar")  # Marathi = 'mar', NOT 'hin'

# Minimum fraction of characters that must be plausible (ASCII or real Unicode
# Devanagari block U+0900-U+097F) for native-extracted text to be trusted.
# Old Maharashtra govt PDFs often use legacy non-Unicode Marathi fonts
# (Shivaji/Kiran/DevLys-style) where get_text() "succeeds" but returns
# mojibake — glyph codes mapped onto random Latin-Extended characters, not
# real Devanagari. Those pages must be forced through OCR (which reads the
# rendered glyph shapes correctly, regardless of the font's internal encoding).
TEXT_QUALITY_MIN_RATIO = 0.85
_DEVANAGARI_START, _DEVANAGARI_END = 0x0900, 0x097F


def _looks_like_real_text(text: str) -> bool:
    """Heuristic: is this native-extracted text plausible Unicode, or is it
    mojibake from a legacy non-Unicode font encoding?"""
    stripped = text.strip()
    if len(stripped) < 20:
        return False
    good = 0
    for ch in stripped:
        cp = ord(ch)
        if cp < 128 or ch.isspace():  # ASCII incl. digits/punctuation/whitespace
            good += 1
        elif _DEVANAGARI_START <= cp <= _DEVANAGARI_END:  # real Devanagari
            good += 1
    ratio = good / len(stripped)
    return ratio >= TEXT_QUALITY_MIN_RATIO
GEMINI_RATE_LIMIT_DELAY = 8.0

# --- Kill switches while Gemini quota is exhausted -----------------------
# Flip both back to False once your Gemini rate limit resets and you want
# Gemini Vision as a genuine rare fallback + Markdown cleanup again.
DISABLE_GEMINI_VISION = True
SKIP_GEMINI_CLEANUP = True
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS documents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name           TEXT NOT NULL,
    file_path           TEXT NOT NULL UNIQUE,
    category            TEXT NOT NULL DEFAULT 'uncategorized',
    language            TEXT NOT NULL DEFAULT 'en',
    checksum_sha256     TEXT,
    total_pages         INT,
    ocr_pages_count     INT DEFAULT 0,
    ingestion_status    TEXT NOT NULL DEFAULT 'pending'
                         CHECK (ingestion_status IN
                             ('pending', 'processing', 'cleaned', 'chunked', 'embedded', 'failed')),
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index         INT  NOT NULL,
    content             TEXT NOT NULL,
    content_char_count  INT GENERATED ALWAYS AS (char_length(content)) STORED,
    category            TEXT NOT NULL DEFAULT 'uncategorized',
    language            TEXT NOT NULL DEFAULT 'en',
    source_page_start   INT,
    source_page_end     INT,
    section_heading     TEXT,
    embedding           vector(1024),
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_document_chunk UNIQUE (document_id, chunk_index),
    CONSTRAINT chk_chunk_not_empty CHECK (char_length(trim(content)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id   ON document_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_category      ON document_chunks (category);
CREATE INDEX IF NOT EXISTS idx_chunks_metadata_gin  ON document_chunks USING GIN (metadata);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON document_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
"""

INSERT_CHUNK_SQL = """
    INSERT INTO document_chunks
        (document_id, chunk_index, content, category, language,
         source_page_start, source_page_end, section_heading, embedding, metadata)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (document_id, chunk_index) DO UPDATE SET
        content            = EXCLUDED.content,
        source_page_start  = EXCLUDED.source_page_start,
        source_page_end    = EXCLUDED.source_page_end,
        section_heading    = EXCLUDED.section_heading,
        embedding           = EXCLUDED.embedding,
        metadata            = EXCLUDED.metadata;
"""

HEADERS_TO_SPLIT_ON = [("#", "h1"), ("##", "h2"), ("###", "h3")]
PAGE_MARKER_RE = re.compile(r"<!-- page:(\d+) -->\s*")


# ============================================================
# Lazy singletons
# ============================================================
_embedding_model: Optional[SentenceTransformer] = None


def get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading embedding model %s on %s ...", EMBEDDING_MODEL_NAME, device)
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)
    return _embedding_model


# ============================================================
# Helper: Page to Image for Gemini Vision
# ============================================================
def _page_to_image_data(page) -> tuple[str, str]:
    """Render pdfplumber page to base64 image for Gemini Vision."""
    pil_image = page.to_image(resolution=300).original.convert("RGB")
    buffer = io.BytesIO()
    pil_image.save(buffer, format="JPEG", quality=95, optimize=True)
    image_bytes = buffer.getvalue()
    return ("image/jpeg", base64.b64encode(image_bytes).decode("utf-8"))


# ============================================================
# Stage 1: PyMuPDF extraction with Tesseract OCR + Gemini Vision fallback
# ============================================================
async def extract_pdf_text(pdf_path: Path) -> list[dict]:
    """Extract text using PyMuPDF native extraction, with pytesseract OCR
    (rendered page image) as the local fallback, and Gemini Vision as the
    last-resort fallback (kill-switched by DISABLE_GEMINI_VISION)."""

    def _extract_sync() -> list[dict]:
        pages_out = []

        try:
            doc = pymupdf.open(pdf_path)
            logger.info(f"Opened PDF with PyMuPDF: {len(doc)} pages")

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_number = page_num + 1

                # 1) Native text extraction (digital PDFs)
                text = page.get_text().strip()
                used_ocr = False
                used_vision = False

                # Reject native text if it's too short OR looks like mojibake
                # from a legacy non-Unicode font (common in old govt Marathi PDFs).
                native_ok = len(text) >= OCR_MIN_CHARS and _looks_like_real_text(text)
                if len(text) >= OCR_MIN_CHARS and not native_ok:
                    logger.info(
                        f"  page {page_number}: native text present ({len(text)} chars) but "
                        f"failed quality check (likely legacy-font mojibake) — forcing OCR"
                    )
                    text = ""  # discard the garbage so it falls through to OCR below

                # 2) Tesseract OCR via rendered pixmap (reliable path — avoids
                #    PyMuPDF's get_textpage_ocr(), which silently returns ""
                #    if TESSDATA_PREFIX isn't resolved correctly).
                if len(text) < OCR_MIN_CHARS:
                    logger.info(f"  page {page_number}: low/rejected text ({len(text)} chars), trying Tesseract OCR")
                    try:
                        pix = page.get_pixmap(dpi=OCR_DPI)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        text = pytesseract.image_to_string(img, lang=TESSERACT_LANG).strip()
                        used_ocr = True
                        logger.info(f"  page {page_number}: Tesseract OCR extracted {len(text)} chars")
                    except Exception as e:
                        logger.warning(f"  page {page_number}: Tesseract OCR failed: {e}")
                        text = ""

                # 3) Still nothing usable -> mark for Gemini Vision fallback
                if len(text) < OCR_MIN_CHARS:
                    logger.info(f"  page {page_number}: insufficient text ({len(text)}), marking for Gemini Vision")
                    used_vision = True
                    image_data = None
                    mime_type = None
                    if not DISABLE_GEMINI_VISION:
                        try:
                            pix = page.get_pixmap(dpi=300)
                            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                            buffer = io.BytesIO()
                            img.save(buffer, format="JPEG", quality=95, optimize=True)
                            image_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
                            mime_type = "image/jpeg"
                        except Exception as e:
                            logger.error(f"  Failed to render page {page_number}: {e}")

                    pages_out.append({
                        "page_number": page_number,
                        "text": text,  # keep whatever partial OCR text we got, if any
                        "used_ocr": used_ocr,
                        "used_vision": used_vision,
                        "image_mime_type": mime_type,
                        "image_data": image_data,
                        "page_obj": None
                    })
                else:
                    pages_out.append({
                        "page_number": page_number,
                        "text": text,
                        "used_ocr": used_ocr,
                        "used_vision": False,
                        "image_mime_type": None,
                        "image_data": None,
                        "page_obj": None
                    })

            doc.close()
            return pages_out

        except Exception as e:
            logger.error(f"PyMuPDF extraction failed: {e}, falling back to pdfplumber+Tesseract/Gemini")
            import traceback
            traceback.print_exc()
            # Fallback path: pdfplumber -> pytesseract -> (optionally) Gemini Vision
            pages_out = []
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    text = (page.extract_text() or "").strip()
                    used_ocr = False
                    used_vision = False

                    if len(text) >= OCR_MIN_CHARS and not _looks_like_real_text(text):
                        logger.info(f"  page {i}: native text failed quality check — forcing OCR")
                        text = ""

                    if len(text) < OCR_MIN_CHARS:
                        try:
                            pil_image = page.to_image(resolution=OCR_DPI).original.convert("RGB")
                            text = pytesseract.image_to_string(pil_image, lang=TESSERACT_LANG).strip()
                            used_ocr = True
                        except Exception as ocr_e:
                            logger.warning(f"  page {i}: pdfplumber Tesseract OCR failed: {ocr_e}")
                            text = ""

                    if len(text) < OCR_MIN_CHARS:
                        used_vision = True
                        image_data = None
                        mime_type = None
                        if not DISABLE_GEMINI_VISION:
                            mime_type, image_data = _page_to_image_data(page)
                        pages_out.append({
                            "page_number": i,
                            "text": text,
                            "used_ocr": used_ocr,
                            "used_vision": True,
                            "image_mime_type": mime_type,
                            "image_data": image_data,
                            "page_obj": None
                        })
                    else:
                        pages_out.append({
                            "page_number": i,
                            "text": text,
                            "used_ocr": used_ocr,
                            "used_vision": False,
                            "image_mime_type": None,
                            "image_data": None,
                            "page_obj": None
                        })
            return pages_out

    return await asyncio.to_thread(_extract_sync)


# ============================================================
# Stage 2: Gemini Vision for fallback pages (kill-switched by default)
# ============================================================
@retry(
    stop=stop_after_attempt(8),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
)
async def _extract_with_gemini_vision(image_data: str, mime_type: str, doc_name: str, page_num: int) -> str:
    """Extract text from scanned page using Gemini Vision API."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set — check your .env")

    prompt = (
        "You are an expert legal document archivist. Extract ALL text from this document image with 100% accuracy.\n\n"
        "CRITICAL REQUIREMENTS:\n"
        "- Extract EVERY word, number, and character EXACTLY as shown on the page\n"
        "- Preserve ALL Marathi (Devanagari) text exactly - NEVER transliterate or translate it\n"
        "- Preserve ALL English text exactly as written\n"
        "- Maintain ALL section numbers (73AAA, 73B, 73C, 73CB, 73F, 81, 157, etc.)\n"
        "- Preserve ALL legal citations: 'Mah. XXIV of 1961', 'Act No. XX of 2026'\n"
        "- Keep ALL punctuation, brackets, and special characters\n"
        "- Maintain the document hierarchy: headers, sections, sub-sections, clauses\n"
        "- Output text in the SAME ORDER as it appears on the page\n"
        "- Do NOT summarize, omit, rephrase, or alter ANY content\n"
        "- Output ONLY the extracted text. No preamble, no explanation, no code fences.\n\n"
        f"DOCUMENT: {doc_name}, PAGE: {page_num}"
    )

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": image_data}}
            ]
        }],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8192},
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(GEMINI_URL, params={"key": GEMINI_API_KEY}, json=payload)
        resp.raise_for_status()
        data = resp.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response shape: {data}") from e


@retry(
    stop=stop_after_attempt(8),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
)
async def _clean_with_gemini(raw_text: str, doc_name: str) -> str:
    """Clean and format text using Gemini (text-only mode)."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set — check your .env")
    if not raw_text.strip():
        return ""

    prompt = (
        "You are a document formatting engine. Convert the following raw, "
        "messy OCR/PDF-extracted text into clean, well-structured Markdown.\n\n"
        "STRICT RULES:\n"
        "- Preserve the content VERBATIM. Do not summarize, translate, omit, or add anything.\n"
        "- Preserve Marathi (Devanagari) text exactly as written; never transliterate or translate it.\n"
        "- Reconstruct headings using Markdown '#'/'##'/'###' based on structural cues.\n"
        "- Reconstruct any tabular data using Markdown pipe-table syntax ('| col | col |').\n"
        "- Fix OCR noise (broken words, stray line breaks) without changing meaning.\n"
        "- Output ONLY the Markdown. No preamble, no explanation, no code fences.\n\n"
        f"--- RAW TEXT (source: {doc_name}) ---\n{raw_text}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8192},
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(GEMINI_URL, params={"key": GEMINI_API_KEY}, json=payload)
        resp.raise_for_status()
        data = resp.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response shape: {data}") from e


def _normalize_whitespace(text: str) -> str:
    """Clean up OCR noise, normalize whitespace, and correct common hyphenations."""
    if not text:
        return ""
    # Remove common OCR noise like standalone | or \ or •
    text = re.sub(r'(?<=\s)[\\/|•*_—](?=\s)', '', text)
    # Correct word hyphenations at line breaks (e.g. co- operative -> cooperative)
    text = re.sub(r'(\b\w+)-\s*\n\s*(\w+\b)', r'\1\2', text)
    # Remove multiple spaces/newlines
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def process_pages_with_gemini(pages: list[dict], doc_name: str) -> str:
    """Process pages into final page-marked text/markdown.

    - Vision-fallback pages: use Gemini Vision, UNLESS DISABLE_GEMINI_VISION
      is True, in which case we keep whatever local OCR text (possibly empty)
      was captured for that page and skip the API call entirely.
    - Normal pages: clean with Gemini text-cleanup, UNLESS SKIP_GEMINI_CLEANUP
      is True, in which case we just whitespace-normalize the raw text locally.
    """
    results = []
    total_pages = len(pages)
    made_any_gemini_call = False

    for idx, page in enumerate(pages):
        if page.get("used_vision", False):
            if DISABLE_GEMINI_VISION:
                fallback_text = page.get("text", "") or ""
                if fallback_text.strip():
                    logger.info(
                        f"  Page {page['page_number']}: vision fallback disabled, "
                        f"keeping {len(fallback_text)} chars of local OCR text"
                    )
                    md = _normalize_whitespace(fallback_text)
                else:
                    logger.warning(
                        f"  Page {page['page_number']}: vision fallback disabled and "
                        f"no local text available — page will be EMPTY"
                    )
                    md = ""
                results.append(f"<!-- page:{page['page_number']} -->\n{md}")
                continue

            image_data = page.get("image_data")
            mime_type = page.get("image_mime_type")
            if image_data is None:
                logger.warning(f"  Page {page['page_number']}: No image data available, skipping")
                results.append(f"<!-- page:{page['page_number']} -->\n")
                continue

            if made_any_gemini_call:
                await asyncio.sleep(GEMINI_RATE_LIMIT_DELAY)
            made_any_gemini_call = True

            md = await _extract_with_gemini_vision(
                image_data, mime_type, doc_name, page["page_number"]
            )
        else:
            if not page["text"].strip():
                md = ""
            elif SKIP_GEMINI_CLEANUP:
                md = _normalize_whitespace(page["text"])
            else:
                if made_any_gemini_call:
                    await asyncio.sleep(GEMINI_RATE_LIMIT_DELAY)
                made_any_gemini_call = True
                md = await _clean_with_gemini(page["text"], doc_name)

        results.append(f"<!-- page:{page['page_number']} -->\n{md}")

        if (idx + 1) % 10 == 0:
            logger.info(f"  Processed {idx + 1}/{total_pages} pages")

    return "\n\n".join(p for p in results if p and p.strip())


# ============================================================
# Stage 3: Hybrid chunking
# ============================================================
def hybrid_chunk_markdown(markdown_with_markers: str) -> list[dict]:
    # Split by paragraphs (\n\n) first
    paragraphs = markdown_with_markers.split("\n\n")
    
    chunks: list[dict] = []
    current_chunk_parts = []
    current_chunk_len = 0
    current_page = 1
    current_heading = None
    
    # Section pattern to detect a new legal section
    # e.g., "Section 73", "कलम ७३", "12. Audit", "CHAPTER IV"
    SECTION_RE = re.compile(
        r"^\s*(?:Section|Sec\.|कलम|CHAPTER|प्रकरण)\s+(\d+|[IVXLCDM]+|[अ-ज्ञ]+)\b"
        r"|^\s*(\d+\.\s+[A-Zअ-ज्ञ])"
    , re.IGNORECASE)
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        # Parse page numbers from this paragraph
        page_hits = [int(p) for p in PAGE_MARKER_RE.findall(para)]
        if page_hits:
            current_page = page_hits[-1]
            
        # Strip page markers from the text for length calculation and storage
        clean_para = PAGE_MARKER_RE.sub("", para).strip()
        if not clean_para:
            continue
            
        # Detect if this paragraph starts a new section or heading
        starts_new_section = bool(SECTION_RE.search(clean_para)) or (len(clean_para) < 100 and clean_para.isupper())
        
        # If we have accumulated text, and we exceed chunk size or hit a new section, emit the chunk
        if current_chunk_parts and (current_chunk_len + len(clean_para) > CHUNK_SIZE or starts_new_section):
            content = "\n\n".join(current_chunk_parts)
            # Find start and end page
            chunk_page_hits = [int(p) for p in PAGE_MARKER_RE.findall(content)]
            page_start = chunk_page_hits[0] if chunk_page_hits else current_page
            page_end = chunk_page_hits[-1] if chunk_page_hits else current_page
            
            chunks.append({
                "content": PAGE_MARKER_RE.sub("", content).strip(),
                "section_heading": current_heading,
                "source_page_start": page_start,
                "source_page_end": page_end,
            })
            
            # Start new chunk with overlap (if not starting a completely new section)
            if not starts_new_section:
                overlap_para = current_chunk_parts[-1]
                current_chunk_parts = [overlap_para, para]
                current_chunk_len = len(overlap_para) + len(para) + 2
            else:
                current_chunk_parts = [para]
                current_chunk_len = len(para)
        else:
            current_chunk_parts.append(para)
            current_chunk_len += len(para) + 2  # +2 for \n\n
            
        # Track heading
        if len(clean_para) < 200 and (clean_para.startswith("#") or clean_para.isupper()):
            current_heading = clean_para.lstrip("#").strip()
            
    # Emit final chunk
    if current_chunk_parts:
        content = "\n\n".join(current_chunk_parts)
        chunk_page_hits = [int(p) for p in PAGE_MARKER_RE.findall(content)]
        page_start = chunk_page_hits[0] if chunk_page_hits else current_page
        page_end = chunk_page_hits[-1] if chunk_page_hits else current_page
        
        chunks.append({
            "content": PAGE_MARKER_RE.sub("", content).strip(),
            "section_heading": current_heading,
            "source_page_start": page_start,
            "source_page_end": page_end,
        })
        
    return chunks


# ============================================================
# Stage 4: Embeddings
# ============================================================
async def embed_chunks(texts: list[str]) -> list[list[float]]:
    def _encode() -> list[list[float]]:
        model = get_embedding_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=16,
            show_progress_bar=False,
        )
        return vectors.tolist()

    return await asyncio.to_thread(_encode)


# ============================================================
# VectorStore
# ============================================================
class VectorStore:
    def __init__(self) -> None:
        self.pool: Optional[AsyncConnectionPool] = None

    async def __aenter__(self) -> "VectorStore":
        await self.init()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def init(self) -> None:
        import psycopg
        with psycopg.connect(PG_DSN) as bootstrap_conn:
            with bootstrap_conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
            bootstrap_conn.commit()
        logger.info("Vector and pgcrypto extensions bootstrapped successfully.")

        async def _configure(conn):
            await register_vector_async(conn)

        self.pool = AsyncConnectionPool(
            PG_DSN, min_size=2, max_size=10, configure=_configure, open=False
        )
        await self.pool.open()

        async with self.pool.connection() as conn:
            await conn.execute(SCHEMA_SQL)
            await conn.commit()

        logger.info("VectorStore initialized — extension, tables, and HNSW index verified.")

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            logger.info("VectorStore connection pool closed.")

    async def _upsert_document(
        self, pdf_path: Path, doc_name: str, category: str, language: str,
        total_pages: int, ocr_pages: int,
    ) -> str:
        checksum = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO documents
                        (file_name, file_path, category, language, checksum_sha256,
                         total_pages, ocr_pages_count, ingestion_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'processing')
                    ON CONFLICT (file_path) DO UPDATE SET
                        checksum_sha256   = EXCLUDED.checksum_sha256,
                        total_pages       = EXCLUDED.total_pages,
                        ocr_pages_count   = EXCLUDED.ocr_pages_count,
                        ingestion_status  = 'processing',
                        error_message     = NULL
                    RETURNING id;
                    """,
                    (doc_name, str(pdf_path), category, language, checksum, total_pages, ocr_pages),
                )
                row = await cur.fetchone()
            await conn.commit()
        return str(row[0])

    async def _mark_status(self, doc_id: str, status: str, error_message: Optional[str] = None) -> None:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE documents SET ingestion_status = %s, error_message = %s WHERE id = %s",
                    (status, error_message, doc_id),
                )
            await conn.commit()

    async def _write_chunks(
        self, doc_id: str, category: str, language: str,
        chunks: list[dict], vectors: list[list[float]],
    ) -> None:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM document_chunks WHERE document_id = %s", (doc_id,))
                for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
                    await cur.execute(
                        INSERT_CHUNK_SQL,
                        (
                            doc_id, idx, chunk["content"], category, language,
                            chunk["source_page_start"], chunk["source_page_end"],
                            chunk["section_heading"], vector,
                            Jsonb({"char_count": len(chunk["content"])}),
                        ),
                    )
                await cur.execute(
                    "UPDATE documents SET ingestion_status = 'embedded' WHERE id = %s", (doc_id,)
                )
            await conn.commit()

    async def process_and_index_pdf(
        self,
        pdf_path: str | Path,
        doc_name: str,
        language: str = "mixed",
        category: str = "uncategorized",
    ) -> dict:
        if self.pool is None:
            raise RuntimeError("VectorStore not initialized — call await store.init() first.")

        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info(
            "[%s] Extracting text (PyMuPDF native + Tesseract OCR%s)...",
            doc_name,
            " + Gemini Vision fallback" if not DISABLE_GEMINI_VISION else " — Gemini Vision DISABLED",
        )
        pages = await extract_pdf_text(pdf_path)
        ocr_pages = sum(1 for p in pages if p.get("used_ocr", False))
        vision_pages = sum(1 for p in pages if p.get("used_vision", False))
        logger.info("[%s] Extracted %d pages (%d local OCR, %d flagged for vision).",
                    doc_name, len(pages), ocr_pages, vision_pages)

        doc_id = await self._upsert_document(pdf_path, doc_name, category, language, len(pages), ocr_pages + vision_pages)

        try:
            logger.info(
                "[%s] Assembling page text (Gemini cleanup %s)...",
                doc_name, "SKIPPED" if SKIP_GEMINI_CLEANUP else f"via {GEMINI_MODEL}"
            )
            markdown = await process_pages_with_gemini(pages, doc_name)

            logger.info("[%s] Chunking markdown...", doc_name)
            chunks = hybrid_chunk_markdown(markdown)
            if not chunks:
                raise RuntimeError("Chunking produced zero chunks — check OCR output for this file")

            logger.info("[%s] Embedding %d chunks...", doc_name, len(chunks))
            vectors = await embed_chunks([c["content"] for c in chunks])

            logger.info("[%s] Writing %d chunks to Postgres...", doc_name, len(chunks))
            await self._write_chunks(doc_id, category, language, chunks, vectors)

            logger.info("[%s] Done. %d chunks indexed.", doc_name, len(chunks))
            return {"document_id": doc_id, "chunks_indexed": len(chunks), "ocr_pages": ocr_pages, "vision_pages": vision_pages}

        except Exception as e:
            logger.exception("[%s] Ingestion failed: %s", doc_name, e)
            await self._mark_status(doc_id, "failed", str(e))
            raise


# ============================================================
# Manual smoke test
# ============================================================
if __name__ == "__main__":
    async def _main():
        async with VectorStore() as store:
            result = await store.process_and_index_pdf(
                pdf_path="./backend/data/raw_store/01_Core_Acts/sample.pdf",
                doc_name="sample.pdf",
                language="mixed",
                category="core_acts",
            )
            print(result)

    asyncio.run(_main())