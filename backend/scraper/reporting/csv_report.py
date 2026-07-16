"""
csv_report.py

Writes the per-run daily report to CSV. Contains ONLY documents processed
during the current scheduler execution — never historical data (the caller
is responsible for passing in only the current run's records).
"""

import csv
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

CSV_COLUMNS: List[str] = [
    "Scraped Date",
    "Scraped Time",
    "Connector",
    "Published Date",
    "Department",
    "Category",
    "Document Type",
    "Title",
    "PDF Name",
    "Source URL",
    "SHA256",
    "Status",
    "S3 Upload",
    "S3 Path",
    "Download Time",
    "Remarks",
]


def write_csv(records: List[Dict], output_path: Path) -> Path:
    """
    Write `records` (list of row dicts matching CSV_COLUMNS) to output_path.

    Raises:
        OSError if the file cannot be written.
    """

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for record in records:
            row = {col: record.get(col, "") for col in CSV_COLUMNS}
            writer.writerow(row)

    logger.info(f"CSV report written: {output_path} ({len(records)} rows)")
    return output_path
