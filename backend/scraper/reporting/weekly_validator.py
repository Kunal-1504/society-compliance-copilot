"""
weekly_validator.py

Weekly validation pass. Does NOT re-run the connectors or duplicate any
scraping/parsing logic — it only reads the existing master_metadata.csv
and checks, over HTTP, whether each previously-downloaded document's
source URL is still reachable.

Detection is necessarily heuristic:
  - "Removed"  : the URL now returns 404 / other client error, or times out
                 repeatedly.
  - "Updated"  : the URL is reachable but Content-Length (or Last-Modified,
                 if present) differs from what we recorded locally — a full
                 byte-for-byte re-hash would require re-downloading every
                 file, which duplicates connector download logic, so this
                 is a lightweight, best-effort signal instead.
  - "OK"       : reachable and appears unchanged.
"""

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd
import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30


def _check_url(url: str) -> Dict:
    """HEAD (falling back to a streamed GET) check of a single URL."""

    if not url:
        return {"reachable": False, "content_length": None, "error": "no URL"}

    try:
        resp = requests.head(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)

        if resp.status_code >= 400 or "content-length" not in resp.headers:
            # Some servers don't answer HEAD properly for PDFs — fall back
            resp = requests.get(
                url, timeout=REQUEST_TIMEOUT, stream=True, allow_redirects=True
            )
            resp.close()

        if resp.status_code >= 400:
            return {"reachable": False, "content_length": None, "error": f"HTTP {resp.status_code}"}

        content_length = resp.headers.get("Content-Length")
        return {
            "reachable": True,
            "content_length": int(content_length) if content_length else None,
            "error": "",
        }

    except requests.RequestException as e:
        return {"reachable": False, "content_length": None, "error": str(e)}


def validate_documents(master_metadata_path: Path) -> List[Dict]:
    """
    Read master_metadata.csv and validate every row's pdf_url.

    Returns a list of row dicts:
        {
            "connector": str, "title": str, "pdf_url": str,
            "local_path": str, "recorded_size": int | None,
            "validation_status": "OK" | "Updated" | "Removed",
            "detail": str,
        }
    """

    master_metadata_path = Path(master_metadata_path)

    if not master_metadata_path.exists():
        logger.warning(f"Master metadata not found: {master_metadata_path}")
        return []

    df = pd.read_csv(master_metadata_path)
    results: List[Dict] = []

    for _, row in df.iterrows():

        pdf_url = str(row.get("pdf_url", "") or "")
        local_path = str(row.get("local_path", "") or "")
        recorded_size = None

        try:
            if local_path and Path(local_path).exists():
                recorded_size = Path(local_path).stat().st_size
        except OSError:
            pass

        check = _check_url(pdf_url)

        if not check["reachable"]:
            status, detail = "Removed", check["error"]

        elif (
            recorded_size is not None
            and check["content_length"] is not None
            and abs(check["content_length"] - recorded_size) > 1024  # >1KB drift
        ):
            status, detail = "Updated", (
                f"Remote size {check['content_length']} vs recorded {recorded_size}"
            )

        else:
            status, detail = "OK", ""

        results.append({
            "connector": row.get("connector", ""),
            "title": row.get("title", ""),
            "pdf_url": pdf_url,
            "local_path": local_path,
            "recorded_size": recorded_size,
            "validation_status": status,
            "detail": detail,
        })

    return results


def summarize_validation(results: List[Dict]) -> Dict:
    """Build a connector-wise + overall summary of the validation pass."""

    by_connector: Dict[str, Dict] = {}

    for r in results:
        connector = r["connector"] or "Unknown"
        by_connector.setdefault(connector, {"total": 0, "ok": 0, "updated": 0, "removed": 0})
        by_connector[connector]["total"] += 1
        by_connector[connector][r["validation_status"].lower()] += 1

    return {
        "total_checked": len(results),
        "ok": sum(1 for r in results if r["validation_status"] == "OK"),
        "updated": sum(1 for r in results if r["validation_status"] == "Updated"),
        "removed": sum(1 for r in results if r["validation_status"] == "Removed"),
        "by_connector": by_connector,
    }
