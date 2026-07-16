"""
Metadata Manager

Stores metadata of all downloaded documents.

Features:
- CSV based metadata
- SHA256 duplicate detection
- Download history
- Master metadata aggregation
"""

from pathlib import Path
from datetime import datetime
import hashlib
import pandas as pd
import logging
from typing import Dict, Optional, List


class MetadataManager:

    def __init__(self, metadata_dir="metadata"):

        self.metadata_dir = Path(metadata_dir)
        self.metadata_dir.mkdir(exist_ok=True)

        self.master_file = self.metadata_dir / "master_metadata.csv"
        self.logger = logging.getLogger(__name__)
        
        # Enhanced columns for RAG citations
        self.columns = [
            # Core identification
            "document_id",
            "title",
            "filename",
            "local_path",
            "pdf_url",
            
            # Source information (CRITICAL for citations)
            "source_website",
            "source_page",
            "department",
            "connector",
            
            # Document classification
            "category",
            "document_type",
            "language",
            
            # Dates
            "date",
            "gr_date",
            "download_date",
            
            # Document details
            "unique_code",
            "size",
            "page_count",
            "version",
            "year",
            "sha256",
            
            # Status
            "status",
            "tags",
            # NEW FIELDS
            "connector_folder",
            "classified_category",
            "classification_confidence",
            "classification_reason",
            "matched_keywords",
            "schema_version",
            "s3_uri",
        ]

        self._initialize()

    def _initialize(self):
        if not self.master_file.exists():
            df = pd.DataFrame(columns=self.columns)
            df.to_csv(self.master_file, index=False)
            self.logger.info(f"Created master metadata: {self.master_file}")
        else:
            # Migrate existing metadata to new schema
            self._migrate_schema()

    def _migrate_schema(self):
        """Add new columns to existing metadata if missing."""
        if not self.master_file.exists():
            return
        
        df = pd.read_csv(self.master_file)
        
        # Add new columns if missing
        new_columns = [
            "connector_folder",
            "classified_category",
            "classification_confidence",
            "classification_reason",
            "matched_keywords",
            "schema_version",
            "s3_uri",
        ]
        
        for col in new_columns:
            if col not in df.columns:
                df[col] = ""
        
        # Set schema version for existing data
        if "schema_version" in df.columns:
            df["schema_version"] = "1.1"
        
        df.to_csv(self.master_file, index=False)
        self.logger.info("Metadata schema migrated to version 1.1")

    def load(self) -> pd.DataFrame:
        """Load master metadata."""
        return pd.read_csv(self.master_file)

    def save(self, df: pd.DataFrame):
        """Save master metadata."""
        df.to_csv(self.master_file, index=False)

    def add_document(self, metadata: Dict) -> bool:
        """
        Add a document to master metadata with SHA256 duplicate detection.
        """
        df = self.load()
        
        # Check for duplicates using SHA256 if available
        sha256 = metadata.get("sha256", "")
        if sha256:
            if not df.empty and sha256 in df["sha256"].values:
                self.logger.info(f"Duplicate SHA256: {sha256}")
                return False
        
        # Also check by PDF URL
        pdf_url = metadata.get("pdf_url", "")
        if pdf_url and not df.empty:
            if pdf_url in df["pdf_url"].values:
                self.logger.info(f"Duplicate URL: {pdf_url}")
                return False
        
        # Add default values for missing fields
        for col in self.columns:
            if col not in metadata:
                metadata[col] = ""
        
        # Ensure datetime format
        if not metadata.get("download_date"):
            metadata["download_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Add to DataFrame
        df = pd.concat([df, pd.DataFrame([metadata])], ignore_index=True)
        self.save(df)
        self.logger.info(f"Added document: {metadata.get('title', 'Untitled')}")
        return True

    def update_download(self, pdf_url: str, filepath: Path, sha256: str = "") -> bool:
        """Update metadata after successful download."""
        df = self.load()
        
        if df.empty:
            return False
        
        # Find by URL
        idx = df.index[df["pdf_url"] == pdf_url]
        if len(idx) == 0:
            # Try by filename
            idx = df.index[df["filename"] == filepath.name]
        
        if len(idx) == 0:
            self.logger.warning(f"Document not found in metadata: {pdf_url}")
            return False
        
        i = idx[0]
        
        # Update fields
        df.loc[i, "filename"] = filepath.name
        df.loc[i, "local_path"] = str(filepath)
        df.loc[i, "download_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df.loc[i, "status"] = "Downloaded"
        
        if sha256:
            df.loc[i, "sha256"] = sha256
        else:
            df.loc[i, "sha256"] = self.calculate_sha256(filepath)
        
        df.loc[i, "size"] = str(filepath.stat().st_size)
        
        self.save(df)
        self.logger.info(f"Updated download: {filepath.name}")
        return True

    def update_metadata(self, pdf_url: str, updates: Dict) -> bool:
        """Update arbitrary metadata fields."""
        df = self.load()
        
        if df.empty:
            return False
        
        idx = df.index[df["pdf_url"] == pdf_url]
        if len(idx) == 0:
            return False
        
        i = idx[0]
        for key, value in updates.items():
            if key in df.columns:
                df.loc[i, key] = value
        
        self.save(df)
        return True

    def get_by_sha256(self, sha256: str) -> Optional[Dict]:
        """Get document by SHA256."""
        df = self.load()
        if df.empty:
            return None
        
        matches = df[df["sha256"] == sha256]
        if not matches.empty:
            return matches.iloc[0].to_dict()
        return None

    def get_by_url(self, pdf_url: str) -> Optional[Dict]:
        """Get document by PDF URL."""
        df = self.load()
        if df.empty:
            return None
        
        matches = df[df["pdf_url"] == pdf_url]
        if not matches.empty:
            return matches.iloc[0].to_dict()
        return None

    def find_duplicate_by_sha256(self, sha256: str) -> List[Dict]:
        """Find all documents with the same SHA256."""
        df = self.load()
        if df.empty:
            return []
        
        matches = df[df["sha256"] == sha256]
        return matches.to_dict('records')

    def get_stats(self) -> Dict:
        """Get metadata statistics."""
        df = self.load()
        
        stats = {
            "total": len(df),
            "downloaded": len(df[df["status"] == "Downloaded"]) if not df.empty else 0,
            "pending": len(df[df["status"] != "Downloaded"]) if not df.empty else 0,
        }
        
        if not df.empty:
            stats["by_connector"] = df["connector"].value_counts().to_dict()
            stats["by_category"] = df["category"].value_counts().to_dict()
            stats["by_document_type"] = df["document_type"].value_counts().to_dict()
            stats["by_language"] = df["language"].value_counts().to_dict()
        
        return stats

    def export_summary(self):
        """Print summary statistics."""
        stats = self.get_stats()
        
        print("\n" + "=" * 70)
        print("MASTER METADATA SUMMARY")
        print("=" * 70)
        print(f"Total Documents    : {stats['total']}")
        print(f"Downloaded         : {stats['downloaded']}")
        print(f"Pending            : {stats['pending']}")
        
        if stats.get("by_connector"):
            print("\nBy Connector:")
            for connector, count in stats["by_connector"].items():
                print(f"  - {connector}: {count}")
        
        if stats.get("by_category"):
            print("\nBy Category:")
            for category, count in stats["by_category"].items():
                print(f"  - {category}: {count}")
        
        if stats.get("by_document_type"):
            print("\nBy Document Type:")
            for doc_type, count in stats["by_document_type"].items():
                print(f"  - {doc_type}: {count}")
        
        print("=" * 70)

    @staticmethod
    def calculate_sha256(filepath: Path):
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()