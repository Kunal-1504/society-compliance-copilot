"""
email_sender.py

Sends the daily/weekly report emails via SMTP, with retry support and
optional attachments (xlsx, csv, and the scheduler log if there were
failures). All SMTP settings come from scheduler.scheduler_config —
nothing hardcoded, no secrets in source.
"""

import logging
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path
from typing import List, Optional

from scheduler.scheduler_config import SchedulerConfig

logger = logging.getLogger(__name__)


def _attach_file(msg: EmailMessage, filepath: Path) -> None:
    filepath = Path(filepath)
    if not filepath.exists():
        logger.warning(f"Attachment not found, skipping: {filepath}")
        return

    data = filepath.read_bytes()

    if filepath.suffix == ".xlsx":
        maintype, subtype = (
            "application",
            "vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    elif filepath.suffix == ".csv":
        maintype, subtype = "text", "csv"
    else:
        maintype, subtype = "application", "octet-stream"

    msg.add_attachment(
        data, maintype=maintype, subtype=subtype, filename=filepath.name
    )


def send_report_email(
    subject: str,
    body: str,
    attachments: Optional[List[Path]] = None,
) -> bool:
    """
    Send an email with the given subject/body and file attachments.
    Retries on transient SMTP errors up to SchedulerConfig.MAX_EMAIL_RETRIES
    times. Returns True on success, False otherwise. Never raises.
    """

    if not SchedulerConfig.EMAIL_ENABLED:
        logger.warning(
            "Email not configured (missing SMTP_HOST/USERNAME/PASSWORD/EMAIL_TO) "
            "— skipping email send"
        )
        return False

    attachments = attachments or []

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SchedulerConfig.EMAIL_FROM
    msg["To"] = ", ".join(SchedulerConfig.EMAIL_TO)
    msg.set_content(body)

    for attachment_path in attachments:
        try:
            _attach_file(msg, attachment_path)
        except Exception as e:
            logger.warning(f"Could not attach {attachment_path}: {e}")

    for attempt in range(1, SchedulerConfig.MAX_EMAIL_RETRIES + 1):

        try:
            with smtplib.SMTP(SchedulerConfig.SMTP_HOST, SchedulerConfig.SMTP_PORT, timeout=30) as server:
                if SchedulerConfig.SMTP_USE_TLS:
                    server.starttls()
                server.login(SchedulerConfig.SMTP_USERNAME, SchedulerConfig.SMTP_PASSWORD)
                server.send_message(msg)

            logger.info(f"Email sent to {SchedulerConfig.EMAIL_TO}: {subject}")
            return True

        except Exception as e:
            logger.warning(
                f"Retry email send {attempt}/{SchedulerConfig.MAX_EMAIL_RETRIES}: {e}"
            )
            if attempt < SchedulerConfig.MAX_EMAIL_RETRIES:
                time.sleep(SchedulerConfig.EMAIL_RETRY_BACKOFF_SECONDS * attempt)

    logger.error(f"ERROR Email send failed after {SchedulerConfig.MAX_EMAIL_RETRIES} attempts")
    return False
