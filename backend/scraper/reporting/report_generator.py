"""
report_generator.py

Builds the daily report (CSV + Excel) from a pipeline result dict
(as returned by main.run_pipeline()), and sends the report email.

This module does not scrape, download, or touch S3 directly — it only
consumes the structured result already produced by the existing pipeline.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from reporting import csv_report, excel_report, email_sender
from scheduler.scheduler_config import SchedulerConfig

logger = logging.getLogger(__name__)


def _split_datetime(value: str) -> Tuple[str, str]:
    """Split a 'YYYY-MM-DD HH:MM:SS' string into (date, time). Safe on bad input."""
    if not value:
        return "", ""
    parts = value.split(" ")
    if len(parts) == 2:
        return parts[0], parts[1]
    return value, ""


def build_daily_records(pipeline_result: Dict) -> List[Dict]:
    """
    Convert pipeline_result["documents"] into the exact row schema required
    by the daily report (CSV_COLUMNS in reporting.csv_report).
    """

    records: List[Dict] = []

    for doc in pipeline_result.get("documents", []):

        scraped_date, scraped_time = _split_datetime(doc.get("download_date", ""))

        local_path = doc.get("local_path", "")
        pdf_name = Path(local_path).name if local_path else doc.get("filename", "")

        status = doc.get("run_status", "Failed")

        remarks = ""
        if status == "Duplicate":
            remarks = "Already present in master metadata (SHA256/URL match)"
        elif status == "Failed":
            remarks = "Missing local_path or SHA256 — download/validation did not complete"

        records.append({
            "Scraped Date": scraped_date,
            "Scraped Time": scraped_time,
            "Connector": doc.get("connector", ""),
            "Published Date": doc.get("gr_date") or doc.get("date", ""),
            "Department": doc.get("department", ""),
            "Category": doc.get("category", ""),
            "Document Type": doc.get("document_type", ""),
            "Title": doc.get("title", ""),
            "PDF Name": pdf_name,
            "Source URL": doc.get("pdf_url", ""),
            "SHA256": doc.get("sha256", ""),
            "Status": status,
            "S3 Upload": "Yes" if doc.get("s3_uploaded") else "No",
            "S3 Path": doc.get("s3_uri", ""),
            # Per-file download timing is not currently instrumented in the
            # connectors (would require a connector-level change, which is
            # out of scope here). Connector-level total duration is
            # available in the Summary sheet instead.
            "Download Time": "N/A",
            "Remarks": remarks,
        })

    return records


def build_summary(pipeline_result: Dict, records: List[Dict]) -> Dict:
    """Build the Summary-sheet dict for the Excel report and email body."""

    start_time: datetime = pipeline_result["start_time"]
    end_time: datetime = pipeline_result["end_time"]
    duration = pipeline_result["duration_seconds"]

    new_count = sum(1 for r in records if r["Status"] == "New")
    duplicate_count = sum(1 for r in records if r["Status"] == "Duplicate")
    failed_count = sum(1 for r in records if r["Status"] == "Failed")
    skipped_count = sum(1 for r in records if r["Status"] == "Skipped")
    s3_uploaded_count = sum(1 for r in records if r["S3 Upload"] == "Yes")

    next_run = _next_scheduled_run(end_time)

    return {
        "Execution Date": start_time.strftime("%Y-%m-%d"),
        "Start Time": start_time.strftime("%H:%M:%S"),
        "End Time": end_time.strftime("%H:%M:%S"),
        "Duration": str(timedelta(seconds=round(duration))),
        "Total Documents Found": len(records),
        "New Documents": new_count,
        "Duplicate Documents": duplicate_count,
        "Failed Documents": failed_count,
        "Skipped Documents": skipped_count,
        "Files Uploaded to S3": s3_uploaded_count,
        "Metadata Updated": new_count,
        "Next Scheduled Run": next_run,
    }


def _next_scheduled_run(after: datetime) -> str:
    """Best-effort description of the next scheduled run time, for the report."""
    times = sorted(SchedulerConfig.DAILY_RUN_TIMES)
    today_times = [
        after.replace(
            hour=int(t.split(":")[0]), minute=int(t.split(":")[1]),
            second=0, microsecond=0,
        )
        for t in times
    ]
    upcoming = [t for t in today_times if t > after]
    if upcoming:
        return upcoming[0].strftime("%Y-%m-%d %H:%M IST")

    tomorrow_first = today_times[0] + timedelta(days=1)
    return tomorrow_first.strftime("%Y-%m-%d %H:%M IST")


def generate_daily_report(pipeline_result: Dict) -> Dict:
    """
    Build daily_report.csv + daily_report.xlsx from a pipeline result, and
    email them. Returns a dict with the paths and summary for logging/tests.
    """

    report_dir = SchedulerConfig.ensure_report_dir()
    date_tag = pipeline_result["start_time"].strftime("%Y-%m-%d")

    records = build_daily_records(pipeline_result)
    summary = build_summary(pipeline_result, records)
    connector_summary = pipeline_result.get("connector_summary", {})

    csv_path = report_dir / f"daily_report_{date_tag}.csv"
    xlsx_path = report_dir / f"daily_report_{date_tag}.xlsx"

    csv_report.write_csv(records, csv_path)
    excel_report.write_excel(records, summary, connector_summary, xlsx_path)

    attachments = [xlsx_path, csv_path]

    has_failures = any(
        stats.get("error") or stats.get("failed", 0) > 0
        for stats in connector_summary.values()
    )
    if has_failures and SchedulerConfig.SCHEDULER_LOG_FILE.exists():
        attachments.append(SchedulerConfig.SCHEDULER_LOG_FILE)

    subject = f"Daily Maharashtra Scraper Report - {date_tag}"
    body = _build_email_body(summary, connector_summary)

    email_sender.send_report_email(subject, body, attachments)

    return {"csv_path": csv_path, "xlsx_path": xlsx_path, "summary": summary}


def _build_email_body(summary: Dict, connector_summary: Dict[str, Dict]) -> str:

    lines = [
        "Maharashtra Government Document Scraper — Execution Summary",
        "=" * 60,
        f"Execution Date : {summary['Execution Date']}",
        f"Start Time     : {summary['Start Time']}",
        f"End Time       : {summary['End Time']}",
        f"Duration       : {summary['Duration']}",
        "",
        f"Total Documents Found : {summary['Total Documents Found']}",
        f"New Documents         : {summary['New Documents']}",
        f"Duplicate Documents   : {summary['Duplicate Documents']}",
        f"Failed Documents      : {summary['Failed Documents']}",
        f"Files Uploaded to S3  : {summary['Files Uploaded to S3']}",
        f"Metadata Updated      : {summary['Metadata Updated']}",
        "",
        "Connector Summary:",
    ]

    for name, stats in connector_summary.items():
        lines.append(
            f"  - {name}: total={stats.get('total', 0)}, "
            f"new={stats.get('new', 0)}, duplicate={stats.get('duplicate', 0)}, "
            f"failed={stats.get('failed', 0)}, duration={stats.get('duration_seconds', 0)}s"
        )
        if stats.get("error"):
            lines.append(f"      ERROR: {stats['error']}")

    lines += [
        "",
        f"Next Scheduled Run: {summary['Next Scheduled Run']}",
        "",
        "Full details attached (daily_report.xlsx / daily_report.csv).",
    ]

    return "\n".join(lines)
