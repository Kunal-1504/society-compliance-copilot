"""
scheduler.py

Production scheduler for the Maharashtra Government Document Collection
Framework.

Runs:
  - The full daily pipeline at 06:00 and 15:00 IST (Asia/Kolkata)
  - A weekly validation pass every Sunday at 02:00 IST

This module ONLY calls existing modules — it does not reimplement any
scraping, downloading, filtering, or S3-upload logic:
  - main.run_pipeline()                for the daily scrape + upload flow
  - reporting.report_generator         for the daily report + email
  - reporting.weekly_validator/report  for the weekly validation + email
"""

import logging
import sys
from pathlib import Path

# Make the project root importable regardless of the working directory
# the scheduler is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from scheduler.scheduler_config import SchedulerConfig

logger = logging.getLogger("scheduler")


def setup_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(SchedulerConfig.SCHEDULER_LOG_FILE, encoding="utf-8"),
            ],
        )


def run_daily_job() -> None:
    """Run the full scraping pipeline once, then generate + email the daily report."""

    import main
    from reporting.report_generator import generate_daily_report

    logger.info("=" * 80)
    logger.info("DAILY SCHEDULED JOB STARTING")
    logger.info("=" * 80)

    try:
        pipeline_result = main.run_pipeline(logger=logging.getLogger("main"))
        generate_daily_report(pipeline_result)
        logger.info("DAILY SCHEDULED JOB COMPLETE")

    except Exception as e:
        logger.exception(f"Daily scheduled job failed: {e}")


def run_weekly_job() -> None:
    """Run the weekly validation pass over existing metadata, then report + email."""

    from config import CONFIG
    from reporting.weekly_validator import validate_documents, summarize_validation
    from reporting.weekly_report import generate_weekly_report

    logger.info("=" * 80)
    logger.info("WEEKLY VALIDATION JOB STARTING")
    logger.info("=" * 80)

    try:
        master_metadata_path = (
            Path(CONFIG["storage"]["metadata_directory"]) / "master_metadata.csv"
        )

        results = validate_documents(master_metadata_path)
        summary = summarize_validation(results)
        generate_weekly_report(results, summary)

        logger.info(
            f"WEEKLY VALIDATION JOB COMPLETE — "
            f"checked={summary['total_checked']}, removed={summary['removed']}, "
            f"updated={summary['updated']}"
        )

    except Exception as e:
        logger.exception(f"Weekly validation job failed: {e}")


def build_scheduler() -> BlockingScheduler:
    """Construct the BlockingScheduler with all cron jobs registered."""

    scheduler = BlockingScheduler(timezone=SchedulerConfig.TIMEZONE)

    for run_time in SchedulerConfig.DAILY_RUN_TIMES:
        hour, minute = run_time.split(":")
        scheduler.add_job(
            run_daily_job,
            trigger=CronTrigger(hour=int(hour), minute=int(minute), timezone=SchedulerConfig.TIMEZONE),
            id=f"daily_job_{run_time.replace(':', '')}",
            name=f"Daily scrape + upload + report ({run_time} IST)",
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )
        logger.info(f"Registered daily job at {run_time} IST")

    weekly_hour, weekly_minute = SchedulerConfig.WEEKLY_RUN_TIME.split(":")
    scheduler.add_job(
        run_weekly_job,
        trigger=CronTrigger(
            day_of_week=SchedulerConfig.WEEKLY_RUN_DAY,
            hour=int(weekly_hour),
            minute=int(weekly_minute),
            timezone=SchedulerConfig.TIMEZONE,
        ),
        id="weekly_validation_job",
        name=f"Weekly validation ({SchedulerConfig.WEEKLY_RUN_DAY} {SchedulerConfig.WEEKLY_RUN_TIME} IST)",
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )
    logger.info(
        f"Registered weekly job on {SchedulerConfig.WEEKLY_RUN_DAY} "
        f"at {SchedulerConfig.WEEKLY_RUN_TIME} IST"
    )

    return scheduler


def main() -> None:
    setup_logging()
    SchedulerConfig.ensure_report_dir()

    logger.info("Starting Maharashtra Scraper Scheduler (Asia/Kolkata)")
    scheduler = build_scheduler()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
