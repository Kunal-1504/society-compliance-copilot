"""
scheduler_config.py

All settings for the scheduler and reporting/email system.
Nothing here duplicates scraper/connector config (config.py, CONFIG dict) —
this only holds scheduling times, report paths, and email/SMTP settings.

All secrets are read from environment variables; nothing is hardcoded.
"""

import os
from pathlib import Path
from typing import List


class SchedulerConfig:

    # ------------------------------------------------------------------
    # Timezone & schedule
    # ------------------------------------------------------------------
    TIMEZONE: str = "Asia/Kolkata"

    # Daily pipeline runs (24h "HH:MM", interpreted in TIMEZONE)
    DAILY_RUN_TIMES: List[str] = ["06:00", "15:00"]

    # Weekly validation run
    WEEKLY_RUN_DAY: str = "sun"       # APScheduler cron day_of_week format
    WEEKLY_RUN_TIME: str = "02:00"

    # ------------------------------------------------------------------
    # Paths (relative to project root; no hardcoded absolute paths)
    # ------------------------------------------------------------------
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
    REPORT_DIR: Path = PROJECT_ROOT / os.environ.get("REPORT_DIR", "reports")
    SCHEDULER_LOG_FILE: Path = PROJECT_ROOT / os.environ.get(
        "SCHEDULER_LOG_FILE", "scheduler.log"
    )

    # ------------------------------------------------------------------
    # Email / SMTP (all from environment variables)
    # ------------------------------------------------------------------
    SMTP_HOST: str = os.environ.get("SMTP_HOST", "")
    SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USE_TLS: bool = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
    SMTP_USERNAME: str = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.environ.get("SMTP_PASSWORD", "")

    EMAIL_FROM: str = os.environ.get("EMAIL_FROM", SMTP_USERNAME)
    EMAIL_TO: List[str] = [
        addr.strip()
        for addr in os.environ.get("EMAIL_TO", "").split(",")
        if addr.strip()
    ]

    EMAIL_ENABLED: bool = bool(SMTP_HOST and SMTP_USERNAME and SMTP_PASSWORD and EMAIL_TO)

    MAX_EMAIL_RETRIES: int = int(os.environ.get("EMAIL_MAX_RETRIES", "3"))
    EMAIL_RETRY_BACKOFF_SECONDS: float = float(
        os.environ.get("EMAIL_RETRY_BACKOFF_SECONDS", "5")
    )

    @classmethod
    def ensure_report_dir(cls) -> Path:
        cls.REPORT_DIR.mkdir(parents=True, exist_ok=True)
        return cls.REPORT_DIR
