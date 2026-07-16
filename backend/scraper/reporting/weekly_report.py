"""
weekly_report.py

Writes the weekly validation report (CSV) and sends the weekly email.
Reuses reporting.email_sender for the actual SMTP send.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from reporting import email_sender
from scheduler.scheduler_config import SchedulerConfig

logger = logging.getLogger(__name__)

WEEKLY_CSV_COLUMNS = [
    "Connector", "Title", "Source URL", "Local Path",
    "Recorded Size", "Validation Status", "Detail",
]


def write_weekly_csv(results: List[Dict], output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(WEEKLY_CSV_COLUMNS)
        for r in results:
            writer.writerow([
                r.get("connector", ""),
                r.get("title", ""),
                r.get("pdf_url", ""),
                r.get("local_path", ""),
                r.get("recorded_size", ""),
                r.get("validation_status", ""),
                r.get("detail", ""),
            ])

    logger.info(f"Weekly report written: {output_path} ({len(results)} rows)")
    return output_path


def generate_weekly_report(results: List[Dict], summary: Dict) -> Dict:
    """Write the weekly CSV report and email it."""

    report_dir = SchedulerConfig.ensure_report_dir()
    date_tag = datetime.now().strftime("%Y-%m-%d")
    csv_path = report_dir / f"weekly_validation_report_{date_tag}.csv"

    write_weekly_csv(results, csv_path)

    subject = f"Weekly Maharashtra Scraper Validation Report - {date_tag}"
    body = _build_weekly_email_body(summary)

    attachments = [csv_path]
    if SchedulerConfig.SCHEDULER_LOG_FILE.exists():
        attachments.append(SchedulerConfig.SCHEDULER_LOG_FILE)

    email_sender.send_report_email(subject, body, attachments)

    return {"csv_path": csv_path, "summary": summary}


def _build_weekly_email_body(summary: Dict) -> str:
    lines = [
        "Maharashtra Government Document Scraper — Weekly Validation Summary",
        "=" * 70,
        f"Total URLs Checked : {summary['total_checked']}",
        f"OK (unchanged)     : {summary['ok']}",
        f"Updated (heuristic): {summary['updated']}",
        f"Removed / broken   : {summary['removed']}",
        "",
        "Connector-wise breakdown:",
    ]

    for connector, stats in summary.get("by_connector", {}).items():
        lines.append(
            f"  - {connector}: total={stats['total']}, ok={stats['ok']}, "
            f"updated={stats['updated']}, removed={stats['removed']}"
        )

    lines += ["", "Full details attached (weekly_validation_report.csv)."]

    return "\n".join(lines)
