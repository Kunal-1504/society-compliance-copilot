"""
Main entry point for Maharashtra Government Document Collection Framework.

`run_pipeline()` is the reusable entry point called both by:
  - `python3 main.py` (manual/standalone run)
  - scheduler/scheduler.py (automated daily runs)

It returns a structured result dict so the reporting layer can build the
daily report and email WITHOUT re-reading connector/downloader internals
or duplicating any scraping logic.
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import CONFIG

from utils.metadata_manager import MetadataManager
from utils.s3_manager import S3Manager

from sources.gr_portal_connector import GRPortalConnector
from sources.cooperation_connector import CooperationConnector
from sources.sahakarayukta_connector import SahakarayuktaConnector
from sources.housing_connector import HousingConnector


CONNECTORS = [
    ("GR Portal", GRPortalConnector),
    ("Cooperation Department", CooperationConnector),
    ("Sahakarayukta", SahakarayuktaConnector),
    ("Housing Department", HousingConnector),
]


def setup_logging(log_file: str = "scraper.log") -> logging.Logger:
    """Setup logging configuration. Safe to call more than once per process."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(log_file, encoding='utf-8')
            ]
        )
    return logging.getLogger(__name__)


def _classify_and_upload(
    documents: List[Dict],
    metadata_manager: Optional[MetadataManager],
    s3_manager: Optional[S3Manager],
    logger: logging.Logger,
) -> None:
    """
    For each document already returned by a connector (i.e. already
    downloaded and validated):
      1. Add it to master metadata -> classify New vs Duplicate
      2. Upload it to S3 (if enabled) and record the s3_uri

    Mutates each document dict in place by adding "run_status" and
    "s3_uploaded" keys, consumed later by the reporting layer.
    """

    for doc in documents:

        doc["run_status"] = "Failed"
        doc["s3_uploaded"] = False

        if not doc.get("local_path") or not doc.get("sha256"):
            continue

        is_new = True
        if metadata_manager:
            try:
                is_new = metadata_manager.add_document(doc)
            except Exception as e:
                logger.warning(f"Could not add to master metadata: {e}")

        doc["run_status"] = "New" if is_new else "Duplicate"

        if s3_manager and s3_manager.enabled:
            try:
                s3_uri = s3_manager.upload_file(doc["local_path"])
                if s3_uri:
                    doc["s3_uploaded"] = True
                    doc["s3_uri"] = s3_uri
                    if metadata_manager:
                        metadata_manager.update_metadata(
                            doc.get("pdf_url", ""), {"s3_uri": s3_uri}
                        )
            except Exception as e:
                logger.warning(f"S3 upload step failed for {doc.get('local_path')}: {e}")


def run_pipeline(logger: Optional[logging.Logger] = None) -> Dict:
    """
    Run every connector once, upload new documents to S3, update metadata.

    Returns a result dict:
        {
            "start_time": datetime,
            "end_time": datetime,
            "duration_seconds": float,
            "documents": [ {...doc fields..., "run_status", "s3_uploaded"} ],
            "connector_summary": {
                "GR Portal": {"total": int, "new": int, "duplicate": int,
                               "failed": int, "duration_seconds": float},
                ...
            },
        }

    This function contains NO scraping logic itself — it only calls each
    connector's existing `.execute()` method.
    """

    logger = logger or setup_logging()

    start_time = datetime.now()

    logger.info("=" * 80)
    logger.info("MAHARASHTRA GOVERNMENT DOCUMENT COLLECTION FRAMEWORK")
    logger.info("=" * 80)

    config = CONFIG

    Path(config["storage"]["dataset_directory"]).mkdir(exist_ok=True)
    Path(config["storage"]["metadata_directory"]).mkdir(exist_ok=True)

    try:
        metadata_manager = MetadataManager(config["storage"]["metadata_directory"])
        logger.info("Master metadata initialized")
    except Exception as e:
        logger.warning(f"Could not initialize master metadata: {e}")
        metadata_manager = None

    try:
        s3_manager = S3Manager(config, logger)
        logger.info(
            f"S3 upload enabled — bucket: {s3_manager.bucket}"
            if s3_manager.enabled else
            "S3 upload disabled (see config['aws']['enabled'])"
        )
    except Exception as e:
        logger.warning(f"Could not initialize S3Manager: {e}")
        s3_manager = None

    all_documents: List[Dict] = []
    connector_summary: Dict[str, Dict] = {}

    for name, connector_cls in CONNECTORS:

        connector_start = time.monotonic()

        try:
            logger.info("\n" + "=" * 80)
            logger.info(f"STARTING {name.upper()} CONNECTOR")
            logger.info("=" * 80)

            connector = connector_cls(config, logger)
            documents = connector.execute()

            _classify_and_upload(documents, metadata_manager, s3_manager, logger)

            all_documents.extend(documents)

            connector_summary[name] = {
                "total": len(documents),
                "new": sum(1 for d in documents if d.get("run_status") == "New"),
                "duplicate": sum(1 for d in documents if d.get("run_status") == "Duplicate"),
                "failed": sum(1 for d in documents if d.get("run_status") == "Failed"),
                "duration_seconds": round(time.monotonic() - connector_start, 2),
            }

            logger.info(f"{name} completed: {len(documents)} documents processed")

        except Exception as e:
            logger.error(f"{name} failed: {e}")
            connector_summary[name] = {
                "total": 0, "new": 0, "duplicate": 0, "failed": 0,
                "duration_seconds": round(time.monotonic() - connector_start, 2),
                "error": str(e),
            }

    if metadata_manager:
        try:
            metadata_manager.export_summary()
        except Exception as e:
            logger.warning(f"Could not export summary: {e}")

    if s3_manager and s3_manager.enabled:
        try:
            s3_manager.upload_metadata()
        except Exception as e:
            logger.warning(f"Could not upload metadata to S3: {e}")

    end_time = datetime.now()

    logger.info("\n" + "=" * 80)
    logger.info("FRAMEWORK EXECUTION COMPLETE")
    logger.info(f"Total documents processed: {len(all_documents)}")
    logger.info("=" * 80)

    return {
        "start_time": start_time,
        "end_time": end_time,
        "duration_seconds": (end_time - start_time).total_seconds(),
        "documents": all_documents,
        "connector_summary": connector_summary,
    }


def main() -> Dict:
    """Standalone CLI entry point — unchanged behavior from before."""
    return run_pipeline()


if __name__ == "__main__":
    main()
