#diagnose_ocr.py

"""
backend/app/services/diagnose_ocr.py

Standalone diagnostic — no VectorStore, no Gemini, no Postgres. Runs
PyMuPDF native extraction and Tesseract OCR directly against a real PDF
and prints everything: environment info, per-page char counts at every
stage, and the FULL exception traceback if anything fails (nothing is
caught-and-summarized here on purpose).

Usage:
    python backend/app/services/diagnose_ocr.py "path/to/Auditor Empanelment Circular.pdf"
"""

import os
import subprocess
import sys
from pathlib import Path

import pymupdf


def print_environment():
    print("=" * 70)
    print("ENVIRONMENT")
    print("=" * 70)
    print(f"pymupdf version   : {pymupdf.__version__}")
    print(f"TESSDATA_PREFIX   : {os.environ.get('TESSDATA_PREFIX', '(not set)')}")

    try:
        result = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=10)
        print(f"tesseract version : {result.stdout.splitlines()[0] if result.stdout else result.stderr.splitlines()[0]}")
    except FileNotFoundError:
        print("tesseract version : NOT FOUND ON PATH (this alone could explain everything)")
    except Exception as e:
        print(f"tesseract version : ERROR checking — {e}")

    try:
        result = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10)
        print(f"tesseract langs   : {result.stdout.strip().splitlines()[1:] if result.stdout else result.stderr}")
    except Exception as e:
        print(f"tesseract langs   : ERROR checking — {e}")

    try:
        tessdata_path = pymupdf.get_tessdata()
        print(f"pymupdf's resolved tessdata path: {tessdata_path}")
        if tessdata_path and os.path.isdir(tessdata_path):
            files = os.listdir(tessdata_path)
            print(f"  contents: {files}")
        else:
            print("  WARNING: this path does not exist or is not a directory")
    except Exception as e:
        print(f"pymupdf.get_tessdata() ERROR: {e}")
    print()


def _text_quality_ratio(text: str) -> float:
    if not text:
        return 0.0
    valid = sum(
        1 for ch in text
        if ch.isspace() or 0x20 <= ord(ch) <= 0x7E or 0x0900 <= ord(ch) <= 0x097F
    )
    return valid / len(text)


def diagnose_pdf(pdf_path: Path):
    print("=" * 70)
    print(f"DIAGNOSING: {pdf_path}")
    print("=" * 70)

    if not pdf_path.exists():
        print(f"FILE NOT FOUND: {pdf_path.resolve()}")
        return

    doc = pymupdf.open(pdf_path)
    print(f"Opened OK. Page count: {len(doc)}\n")

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_number = page_num + 1
        print(f"--- Page {page_number} ---")

        # 1) Native text
        native_text = page.get_text().strip()
        quality = _text_quality_ratio(native_text)
        will_ocr = len(native_text) < 100 or quality < 0.85
        print(f"  native get_text(): {len(native_text)} chars, quality_ratio={quality:.2f}")
        print(f"  -> pipeline decision: {'WILL trigger OCR (unusable)' if will_ocr else 'WILL use native text (usable)'}")
        if native_text:
            print(f"    preview: {native_text[:120]!r}")

        # 2) What does the page actually render as? Save it so you can look at it.
        pix = page.get_pixmap(dpi=300)
        out_img = f"/tmp/diagnose_page_{page_number}.png"
        pix.save(out_img)
        print(f"  rendered page image saved to: {out_img}  (OPEN THIS to confirm the scan is actually legible)")
        print(f"    pixmap size: {pix.width}x{pix.height}, samples len: {len(pix.samples)}")

        # 3) OCR — NO try/except here. If this fails, we want the full traceback.
        print(f"  running get_textpage_ocr(language='eng+hin+mar', dpi=300, full=True)...")
        textpage = page.get_textpage_ocr(language="eng+hin+mar", dpi=300, full=True)
        ocr_text = textpage.extractText().strip()
        print(f"  OCR result: {len(ocr_text)} chars")
        if ocr_text:
            print(f"    preview: {ocr_text[:200]!r}")
        else:
            print("    *** ZERO CHARS — this is the actual reproduction of your issue ***")

        print()

    doc.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python diagnose_ocr.py <path-to-pdf>")
        sys.exit(1)

    print_environment()
    diagnose_pdf(Path(sys.argv[1]))