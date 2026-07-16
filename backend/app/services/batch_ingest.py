#batch_ingest.py

"""
app/services/batch_ingest.py

Multi-threaded batch ingestion for Maharashtra Cooperative Housing Society documents.
Walks through folder structure and processes PDFs using the VectorStore pipeline.

No logic changes were needed here — the extraction bugs were entirely inside
vector_store.py. This file is included unchanged (aside from this note) so you
have the full matching pair.
"""

import sys
from pathlib import Path

# Fix for NumPy 2.0 compatibility - MUST be before any numpy imports
import numpy as np
if not hasattr(np, "sctypes"):
    np.sctypes = {
        "float": [np.float16, np.float32, np.float64],
        "int": [np.int8, np.int16, np.int32, np.int64],
        "uint": [np.uint8, np.uint16, np.uint32, np.uint64],
        "others": [bool, complex, object, str, bytes]
    }
if not hasattr(np, "long"): np.long = int

# Add backend to Python path so 'app' module can be found
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import argparse
import logging
import time
from typing import List, Dict, Optional
from tqdm.asyncio import tqdm

from app.services.vector_store import VectorStore
from config.manifest import CATEGORY_MAPPINGS, DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("batch_ingest")


class BatchIngestionService:
    """Handles batch processing of PDFs from the raw_store folder structure."""

    def __init__(self, category_filter: Optional[str] = None,
                 file_filter: Optional[str] = None,
                 concurrency: int = 2, dry_run: bool = False):
        self.category_filter = category_filter
        self.file_filter = file_filter
        self.concurrency = concurrency
        self.dry_run = dry_run
        self.vector_store = VectorStore()
        self.results: List[Dict] = []
        self.failed: List[Dict] = []
        self.skipped: List[Dict] = []

    def _get_category_from_folder(self, folder_name: str) -> str:
        """Map folder name to category using manifest."""
        return CATEGORY_MAPPINGS.get(folder_name, "uncategorized")

    def _get_language_from_folder(self, folder_name: str) -> str:
        """Determine language based on folder name."""
        if "marathi" in folder_name.lower():
            return "mr"
        elif "english" in folder_name.lower():
            return "en"
        return "mixed"

    def _scan_pdfs(self) -> List[Dict]:
        """Walk through raw_store and collect PDFs."""
        pdf_files = []
        raw_store_path = Path(DATA_DIR) / "raw_store"

        if not raw_store_path.exists():
            logger.error(f"Raw store path not found: {raw_store_path}")
            return []

        for folder in raw_store_path.iterdir():
            if not folder.is_dir():
                continue

            folder_name = folder.name

            # Filter by category if specified
            if self.category_filter and self.category_filter != folder_name:
                continue

            category = self._get_category_from_folder(folder_name)
            language = self._get_language_from_folder(folder_name)

            for pdf_path in folder.glob("*.pdf"):
                # Filter by specific file name if specified
                if self.file_filter:
                    # Match exact filename or partial match
                    if self.file_filter not in pdf_path.name:
                        continue

                pdf_files.append({
                    "path": pdf_path,
                    "doc_name": pdf_path.name,
                    "category": category,
                    "language": language,
                    "folder": folder_name
                })

        logger.info(f"Matched {len(pdf_files)} file(s) to evaluate. Concurrency={self.concurrency}")
        return pdf_files

    async def _process_single(self, file_info: Dict, semaphore: asyncio.Semaphore) -> Dict:
        """Process a single PDF with concurrency control."""
        async with semaphore:
            try:
                logger.info(f"PROCESSING: {file_info['doc_name']} [folder={file_info['folder']}, category={file_info['category']}, language={file_info['language']}]")

                if self.dry_run:
                    return {
                        "file": file_info['doc_name'],
                        "status": "dry_run",
                        "message": "Dry run - skipped processing"
                    }

                result = await self.vector_store.process_and_index_pdf(
                    pdf_path=file_info['path'],
                    doc_name=file_info['doc_name'],
                    language=file_info['language'],
                    category=file_info['category']
                )

                return {
                    "file": file_info['doc_name'],
                    "status": "success",
                    "chunks": result.get('chunks_indexed', 0),
                    "ocr_pages": result.get('ocr_pages', 0),
                    "vision_pages": result.get('vision_pages', 0),
                }

            except Exception as e:
                logger.error(f"FAILED: {file_info['doc_name']} -> {e}")
                return {
                    "file": file_info['doc_name'],
                    "status": "failed",
                    "error": str(e)
                }

    async def run(self) -> Dict:
        """Run the batch ingestion process."""
        start_time = time.time()
        pdf_files = self._scan_pdfs()

        if not pdf_files:
            logger.warning("No PDF files found to process.")
            return self._summary(start_time)

        # Initialize vector store
        await self.vector_store.init()

        # Process with concurrency control
        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = [self._process_single(f, semaphore) for f in pdf_files]

        # Process with progress bar
        results = []
        for coro in tqdm.as_completed(tasks, total=len(tasks), desc="Ingesting"):
            result = await coro
            results.append(result)

        # Categorize results
        for r in results:
            if r["status"] == "success":
                self.results.append(r)
            elif r["status"] == "failed":
                self.failed.append(r)
            else:
                self.skipped.append(r)

        # Close vector store
        await self.vector_store.close()

        return self._summary(start_time)

    def _summary(self, start_time: float) -> Dict:
        """Generate summary of batch ingestion."""
        elapsed = time.time() - start_time
        total_chunks = sum(r.get('chunks', 0) for r in self.results)
        total_ocr_pages = sum(r.get('ocr_pages', 0) for r in self.results)
        total_vision_pages = sum(r.get('vision_pages', 0) for r in self.results)

        print("\n" + "=" * 60)
        print("BATCH INGESTION SUMMARY")
        print("=" * 60)
        print(f"  Processed : {len(self.results)}  ({total_chunks} chunks indexed)")
        print(f"  Local OCR pages   : {total_ocr_pages}")
        print(f"  Vision fallback pages (flagged, may be 0 chars if disabled) : {total_vision_pages}")
        print(f"  Skipped   : {len(self.skipped)}")
        print(f"  Failed    : {len(self.failed)}")
        print(f"  Elapsed   : {elapsed:.1f}s")
        print()

        if self.failed:
            print("  Failures:")
            for f in self.failed:
                print(f"    - {f['file']}: {f.get('error', 'Unknown error')}")
        print("=" * 60)

        return {
            "processed": len(self.results),
            "total_chunks": total_chunks,
            "skipped": len(self.skipped),
            "failed": len(self.failed),
            "elapsed": elapsed,
            "failures": [f['file'] for f in self.failed]
        }


def main():
    parser = argparse.ArgumentParser(description="Batch ingest PDFs for RAG pipeline")
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Category folder to process (e.g., 01_Core_Acts). If not specified, process all."
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Specific PDF filename to process (partial match allowed, e.g., 'MCS1960')"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of concurrent PDFs to process (default: 1)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and show files without processing"
    )

    args = parser.parse_args()

    service = BatchIngestionService(
        category_filter=args.category,
        file_filter=args.file,
        concurrency=args.concurrency,
        dry_run=args.dry_run
    )

    result = asyncio.run(service.run())

    # Exit with error code if any failures
    if result.get("failed", 0) > 0:
        exit(1)
    exit(0)


if __name__ == "__main__":
    main()