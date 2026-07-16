"""
3-Phase Dataset Migration

Phase 1: Analyze - Generate migration_report.csv
Phase 2: Review - Human checks report
Phase 3: Move - Execute migration with rollback support
"""

import argparse
import csv
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from config import CONFIG
from core.category_classifier import CategoryClassifier


class DatasetMigrator:
    """3-Phase migration with rollback support."""

    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.classifier = CategoryClassifier(config)
        
        self.dataset_path = Path(config["storage"]["dataset_directory"])
        self.metadata_dir = Path(config["storage"]["metadata_directory"])
        self.metadata_file = self.metadata_dir / "master_metadata.csv"
        self.backup_dir = self.metadata_dir / "backups"
        self.report_dir = self.metadata_dir / "reports"
        
        self.stats = {
            "total": 0,
            "analyzed": 0,
            "moved": 0,
            "skipped": 0,
            "failed": 0,
            "duplicates": 0,
        }

    def analyze(self) -> str:
        """
        Phase 1: Analyze and generate report.
        
        Returns:
            Path to migration report CSV.
        """
        self.logger.info("=" * 70)
        self.logger.info("PHASE 1: ANALYSIS")
        self.logger.info("=" * 70)

        # Load metadata
        df = self._load_metadata()
        if df is None:
            return ""

        self.stats["total"] = len(df)

        # Create report
        report_rows = []
        for idx, row in df.iterrows():
            doc = row.to_dict()
            local_path = row.get("local_path", "")
            
            if not local_path or pd.isna(local_path):
                continue

            filepath = Path(local_path)
            if not filepath.exists():
                continue

            # Classify
            result = self.classifier.classify(doc)
            current_folder = filepath.parent.name

            report_rows.append({
                "document_id": row.get("document_id", ""),
                "title": row.get("title", ""),
                "current_folder": current_folder,
                "proposed_category": result.category,
                "confidence": result.confidence,
                "reason": result.reason,
                "matched_keywords": ",".join(result.matched_keywords) if result.matched_keywords else "",
                "current_path": str(filepath),
                "proposed_path": str(self.dataset_path / result.category / filepath.name),
                "exists_at_proposed": str((self.dataset_path / result.category / filepath.name).exists()),
            })

            self.stats["analyzed"] += 1

        # Save report
        self.report_dir.mkdir(parents=True, exist_ok=True)
        report_file = self.report_dir / f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        with open(report_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=report_rows[0].keys())
            writer.writeheader()
            writer.writerows(report_rows)

        self.logger.info(f"Report saved: {report_file}")
        self.logger.info(f"Analyzed {self.stats['analyzed']} documents")

        return str(report_file)

    def migrate(self, dry_run: bool = False) -> None:
        """
        Phase 3: Execute migration.
        
        Args:
            dry_run: If True, simulate without moving files.
        """
        self.logger.info("=" * 70)
        self.logger.info("PHASE 3: MIGRATION" + (" (DRY RUN)" if dry_run else ""))
        self.logger.info("=" * 70)

        # Create backup
        self._create_backup()

        # Load metadata
        df = self._load_metadata()
        if df is None:
            return

        # Process each document
        for idx, row in df.iterrows():
            self._process_document(idx, row, df, dry_run)

        # Save metadata
        df.to_csv(self.metadata_file, index=False)

        # Summary
        self._print_summary()

    def _process_document(self, idx: int, row: pd.Series, df: pd.DataFrame, dry_run: bool):
        """Process a single document."""
        local_path = row.get("local_path", "")
        if not local_path or pd.isna(local_path):
            self.stats["skipped"] += 1
            return

        filepath = Path(local_path)
        if not filepath.exists():
            self.stats["skipped"] += 1
            return

        # Classify
        doc = row.to_dict()
        result = self.classifier.classify(doc)

        # If confidence too low, use Unknown
        if result.confidence < CONFIG.get("MIN_CONFIDENCE", 0.3):
            category = "Unknown"
            reason = f"Low confidence: {result.confidence:.2f}"
        else:
            category = result.category
            reason = result.reason

        # Check if already in correct folder
        current_folder = filepath.parent.name
        if current_folder == category:
            self.stats["skipped"] += 1
            return

        # Determine target
        target_dir = self.dataset_path / category
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filepath.name

        # Duplicate detection using SHA256
        existing_sha = row.get("sha256", "")
        if existing_sha:
            # Check if any document with same SHA256 exists
            duplicates = df[df["sha256"] == existing_sha]
            if len(duplicates) > 1:
                self.logger.warning(f"SHA256 duplicate: {filepath.name}")
                self.stats["duplicates"] += 1
                return

        if dry_run:
            self.logger.info(f"[DRY RUN] Would move: {filepath.name} -> {category}/")
            self.stats["moved"] += 1
            return

        # Actually move
        try:
            shutil.move(str(filepath), str(target_path))
            df.loc[idx, "local_path"] = str(target_path)
            df.loc[idx, "connector_folder"] = current_folder
            df.loc[idx, "classified_category"] = category
            df.loc[idx, "classification_confidence"] = result.confidence
            df.loc[idx, "classification_reason"] = reason
            df.loc[idx, "matched_keywords"] = ",".join(result.matched_keywords) if result.matched_keywords else ""
            df.loc[idx, "schema_version"] = "1.1"
            self.stats["moved"] += 1
            self.logger.info(f"Moved: {filepath.name} -> {category}/")
        except Exception as e:
            self.logger.error(f"Failed to move {filepath.name}: {e}")
            self.stats["failed"] += 1

    def _load_metadata(self) -> Optional[pd.DataFrame]:
        """Load metadata file."""
        if not self.metadata_file.exists():
            self.logger.error(f"Metadata file not found: {self.metadata_file}")
            return None
        
        df = pd.read_csv(self.metadata_file)
        self.logger.info(f"Loaded {len(df)} documents")
        return df

    def _create_backup(self) -> None:
        """Create backup of metadata file."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"metadata_backup_{timestamp}.csv"
        shutil.copy2(self.metadata_file, backup_file)
        self.logger.info(f"Backup created: {backup_file}")

    def _print_summary(self) -> None:
        """Print migration summary."""
        self.logger.info("=" * 70)
        self.logger.info("MIGRATION SUMMARY")
        self.logger.info("=" * 70)
        self.logger.info(f"Total Documents:    {self.stats['total']}")
        self.logger.info(f"Successfully Moved: {self.stats['moved']}")
        self.logger.info(f"Skipped:            {self.stats['skipped']}")
        self.logger.info(f"Duplicates:         {self.stats['duplicates']}")
        self.logger.info(f"Failed:             {self.stats['failed']}")
        self.logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="3-Phase Dataset Migration")
    parser.add_argument("--phase", choices=["analyze", "migrate"], required=True)
    parser.add_argument("--dry-run", action="store_true", help="Simulate without moving files")
    parser.add_argument("--report", help="Report file to use for migration")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    migrator = DatasetMigrator(CONFIG)
    
    if args.phase == "analyze":
        migrator.analyze()
    elif args.phase == "migrate":
        if args.dry_run:
            print("\n⚠️  DRY RUN - No files will be moved\n")
        migrator.migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()