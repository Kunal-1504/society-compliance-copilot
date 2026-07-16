"""
base_connector.py

Abstract base class for all Maharashtra Government document connectors.

Every source (GR Portal, Registrar, Gazette, Housing Department,
MAHARERA, etc.) should inherit from this class.

Author: Housing Society Document Collection Framework
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any
import hashlib
import logging
import requests
import re
from datetime import datetime


class BaseConnector(ABC):
    """
    Base class for every government website connector.
    """

    def __init__(self, config: Dict):

        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.session = requests.Session()
        self._classifier = None
        self.session.headers.update({
            "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/137.0 Safari/537.36"
        })

        self.timeout = config.get("timeout", 30)
        self.verify_ssl = config.get("verify_ssl", False)

        self.dataset_path = Path(config.get("dataset_path", "dataset"))
        self.dataset_path.mkdir(exist_ok=True)

        self.logger = logging.getLogger(self.__class__.__name__)
        
                # Lazy classifier - only initialized when needed
        self._classifier = None
        # Document counter for generating unique IDs
        self._doc_counter = 0

    ####################################################################
    # Required Methods
    ####################################################################

    @abstractmethod
    def scrape(self) -> List[Dict]:
        """
        Discover available documents.

        Returns:
            [
                {
                    "title": "...",
                    "department":"...",
                    "pdf_url":"...",
                    "date":"...",
                    "language":"English",
                    "category":"Government Resolution"
                }
            ]
        """
        pass

    ####################################################################
    # HTTP Helpers
    ####################################################################

    def get(self, url: str):
        self.logger.info(f"GET {url}")
        response = self.session.get(
            url,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        return response

    def post(self, url: str, data: Dict):
        self.logger.info(f"POST {url}")
        response = self.session.post(
            url,
            data=data,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        return response

    ####################################################################
    # Download with Validation
    ####################################################################

    def download_pdf(
        self,
        pdf_url: str,
        filename: str,
        folder: str = "Government_Resolutions"
    ) -> Optional[Path]:

        folder_path = self.dataset_path / folder
        folder_path.mkdir(parents=True, exist_ok=True)

        filepath = folder_path / filename

        if filepath.exists():
            self.logger.info(f"Already exists: {filename}")
            return filepath

        try:
            r = self.session.get(
                pdf_url,
                timeout=60,
                verify=self.verify_ssl,
                stream=True
            )
            r.raise_for_status()

            # Check Content-Type
            content_type = r.headers.get('Content-Type', '').lower()
            if 'pdf' not in content_type and 'application' not in content_type:
                self.logger.warning(f"Not PDF content-type: {content_type}")
                return None

            # Check content length
            content_length = r.headers.get('Content-Length')
            if content_length and int(content_length) < 1024:  # Less than 1KB
                self.logger.warning(f"File too small: {content_length} bytes")
                return None

            # Download
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)

            # Validate downloaded PDF
            if not self._validate_pdf(filepath):
                filepath.unlink(missing_ok=True)
                self.logger.warning(f"Invalid PDF: {filename}")
                return None

            self.logger.info(f"Downloaded {filename}")
            return filepath

        except Exception as e:
            self.logger.error(f"Download failed for {pdf_url}: {e}")
            return None

    ####################################################################
    # PDF Validation
    ####################################################################

    def _validate_pdf(self, filepath: Path) -> bool:
        """Validate that the file is a genuine PDF."""
        try:
            # Check file exists and has reasonable size
            if not filepath.exists():
                return False
            if filepath.stat().st_size < 1024:  # Less than 1KB
                return False
            if filepath.stat().st_size > 50 * 1024 * 1024:  # Larger than 50MB
                self.logger.warning(f"File too large: {filepath.stat().st_size} bytes")
                return False

            # Check PDF header
            with open(filepath, "rb") as f:
                header = f.read(8)
                if header[:4] == b'%PDF':
                    return True
                # Also check for common HTML error pages
                if b'<html' in header.lower() or b'<!DOCTYPE' in header.lower():
                    self.logger.warning("File contains HTML instead of PDF")
                    return False
                self.logger.warning(f"Invalid PDF header: {header[:8]}")
                return False
        except Exception as e:
            self.logger.warning(f"PDF validation error: {e}")
            return False

    ####################################################################
    # Enhanced Metadata Creation
    ####################################################################

    def create_document_metadata(
        self,
        doc: Dict,
        connector_name: str,
        source_website: str
    ) -> Dict:
        """
        Create enhanced metadata for each document with all required fields.
        """
        self._doc_counter += 1
        
        # Generate a unique document ID
        doc_id = f"{connector_name.lower().replace(' ', '_')}_{self._doc_counter:06d}"
        
        # Get title
        title = doc.get("title", "Untitled")
        
        # Get date, try to parse it
        date_str = doc.get("date", "")
        gr_date = self._normalize_date(date_str) if date_str else ""
        
        # Determine document type from title
        doc_type = self._detect_document_type(title)
        
        # Get category
        category = doc.get("category", "Unknown")
        
        # Get language
        language = doc.get("language", "Unknown")
        
        # Get department
        department = doc.get("department", connector_name)
        
        # Get unique code if available (GR Portal)
        unique_code = doc.get("unique_code", "")
        
        # Get size
        file_size = doc.get("size", "")
        
        # Build source metadata
        source_metadata = {
            "source_website": source_website,
            "source_page": doc.get("source_page", ""),
            "connector": connector_name,
            "department": department,
            "category": category,
            "document_type": doc_type,
        }
        
        # Return complete metadata
        return {
            # New enhanced fields
            "document_id": doc_id,
            "source_website": source_website,
            "connector": connector_name,
            "document_type": doc_type,
            "page_count": 0,  # Will be updated later by OCR pipeline
            "gr_date": gr_date,
            
            # Existing fields (preserved)
            "title": title,
            "filename": "",  # Will be set after download
            "local_path": "",  # Will be set after download
            "pdf_url": doc.get("pdf_url", ""),
            "department": department,
            "category": category,
            "language": language,
            "date": date_str,
            "unique_code": unique_code,
            "size": file_size,
            "sha256": "",  # Will be set after download
            "download_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "Discovered",
            "source_page": doc.get("source_page", ""),
            "tags": self._extract_tags(title, category),
        }

    ####################################################################
    # Helper Methods for Metadata
    ####################################################################

    def _detect_document_type(self, title: str) -> str:
        """Detect document type from title."""
        title_lower = title.lower()
        
        type_patterns = {
            "Act": ["act", "अधिनियम", "legislation", "statute"],
            "Rule": ["rule", "rules", "नियम", "regulation"],
            "Bye-law": ["bye-law", "byelaw", "by law", "उपविधी", "model bye-laws"],
            "Government Resolution": ["gr", "government resolution", "शासन निर्णय", "notification"],
            "Circular": ["circular", "परिपत्रक", "परिपत्र"],
            "Guideline": ["guideline", "guidelines", "मार्गदर्शक"],
            "Policy": ["policy", "धोरण", "scheme"],
            "Report": ["report", "अहवाल", "audit report"],
            "Election": ["election", "निवडणूक", "poll"],
            "Redevelopment": ["redevelopment", "पुनर्विकास", "reconstruction"],
            "Conveyance": ["conveyance", "अभिहस्तांतरण", "transfer of title"],
            "Minutes": ["minutes", "मिनिटे", "mom", "meeting"],
            "Audit": ["audit", "लेखापरीक्षण", "auditor"],
            "Annual Return": ["annual return", "वार्षिक अहवाल"],
            "Amendment": ["amendment", "सुधारणा", "amendment act"],
        }
        
        for doc_type, keywords in type_patterns.items():
            for keyword in keywords:
                if keyword in title_lower:
                    return doc_type
        
        return "Other"

    def _extract_tags(self, title: str, category: str) -> List[str]:
        """Extract relevant tags from title and category."""
        tags = []
        text = (title + " " + category).lower()
        
        tag_keywords = [
            "housing", "society", "cooperative", "redevelopment", 
            "conveyance", "audit", "election", "committee",
            "member", "registration", "annual return", "agm",
            "bye-law", "mcs act", "rera", "mhada", "slum",
            "rent control", "apartment", "flat", "building",
            "गृहनिर्माण", "सहकार", "संस्था", "पुनर्विकास"
        ]
        
        for keyword in tag_keywords:
            if keyword in text:
                tags.append(keyword.replace(" ", "_"))
        
        return tags[:5]  # Limit to 5 tags

    def _normalize_date(self, date_str: str) -> str:
        """Normalize date to YYYY-MM-DD format."""
        if not date_str:
            return ""
        
        # Try various date formats
        patterns = [
            (r'(\d{2})[/-](\d{2})[/-](\d{4})', r'\3-\2-\1'),
            (r'(\d{4})[/-](\d{2})[/-](\d{2})', r'\1-\2-\3'),
            (r'(\d{2})[/-](\d{2})[/-](\d{2})', r'20\3-\2-\1'),
        ]
        
        for pattern, replacement in patterns:
            if re.search(pattern, date_str):
                return re.sub(pattern, replacement, date_str)
        
        return date_str

    ####################################################################
    # SHA256
    ####################################################################

    @staticmethod
    def calculate_sha256(filepath: Path):
        sha = hashlib.sha256()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()

    ####################################################################
    # Filename
    ####################################################################

    @staticmethod
    def sanitize_filename(name: str):
        invalid = '<>:"/\\|?*'
        for ch in invalid:
            name = name.replace(ch, "_")
        return name.strip()

    ####################################################################
    # Logging
    ####################################################################

    def info(self, msg: str):
        self.logger.info(msg)

    def warning(self, msg: str):
        self.logger.warning(msg)

    def error(self, msg: str):
        self.logger.error(msg)

    @property
    def classifier(self):
        """Lazy initialization of category classifier."""
        if self._classifier is None:
            try:
                from core.category_classifier import CategoryClassifier
                self._classifier = CategoryClassifier(self.config)
            except Exception as e:
                self.logger.debug(f"Category classifier not available: {e}")
        return self._classifier

    def get_category_folder(self, document: Dict) -> str:
        """Get category folder for document using classifier."""
        if self.classifier:
            try:
                return self.classifier.get_category_for_download(document)
            except Exception as e:
                self.logger.warning(f"Classification failed: {e}")
        return "Unknown"