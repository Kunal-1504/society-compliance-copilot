"""
Housing Department Connector

Scrapes:
https://housing.maharashtra.gov.in/en/documents/

Sections:
- Acts & Rules
- Minutes of Meeting
- Circulars
- Notifications
- GRs
- Schemes

Housing Society Focused
"""

import re
import time
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from core.base_connector import BaseConnector


class HousingConnector(BaseConnector):

    def __init__(self, config, logger):

        super().__init__(config)

        self.logger = logger
        self.config = config

        self.name = "Housing Department"
        self.source_website = "https://housing.maharashtra.gov.in"
        self.department = "Housing Department"

        self.base_url = config["housing"]["base_url"]
        self.documents_url = config["housing"]["documents_url"]

        # Category URLs - same pattern as Cooperation Department
        self.category_urls = {
            "Acts & Rules": f"{self.documents_url}acts-rules/",
            "Minutes of Meeting": f"{self.documents_url}minutes-of-meeting/",
            # Add more categories as discovered
            # "Circulars": f"{self.documents_url}circulars/",
            # "Notifications": f"{self.documents_url}notifications/",
            # "Government Resolutions": f"{self.documents_url}government-resolutions/",
            # "Schemes": f"{self.documents_url}schemes/",
        }

        self.max_pages = config["housing"].get("max_pages", 50)
        self.sleep = config["housing"].get("delay", 2)

        self.current_page = 1
        self.current_category = ""
        self.current_category_url = ""

        self.documents = []
        self.visited_pdf_urls = set()

        # Housing Department Keywords (for relevance filtering)
        self.housing_keywords = [
            # Housing Acts
            "maharashtra housing",
            "housing act",
            "rent control",
            "rent act",
            "slum",
            "slum rehabilitation",
            "slum clearance",
            "redevelopment",
            "maharashtra housing and area development",
            "mhada",
            "real estate",
            "rera",
            "apartment ownership",
            "ownership flats",
            "government premises",
            "eviction",
            "housing society",
            "housing rules",
            "housing regulation",
            "development control",
            "building",
            "construction",
            "grievance redressal",
            "housing department",
            "gृह",
            "गृहनिर्माण",
            "झोपडपट्टी",
            "पुनर्विकास",
            "भाडे",
            "मालकी",
            "महाडा",
            "स्लम",
        ]

        # Keywords to EXCLUDE (non-housing)
        self.exclude_keywords = [
            "agriculture",
            "crop",
            "fisheries",
            "dairy",
            "animal",
            "poultry",
            "sugar",
            "cooperative",
            "credit",
            "loan",
            "promotion",
            "seniority",
            "employee",
            "staff",
            "recruitment",
            "tender",
            "procurement",
            "budget",
        ]

    ##################################################################
    # MAIN ENTRY
    ##################################################################

    def scrape(self):

        self.info("=" * 70)
        self.info("Housing Department - Housing Focus")
        self.info("=" * 70)

        for category_name, category_url in self.category_urls.items():

            self.info(f"\n--- Category: {category_name} ---")
            self.current_category = category_name
            self.current_category_url = category_url
            self.current_page = 1

            try:
                html = self.fetch_page(category_url)
            except Exception as e:
                self.warning(f"Failed to fetch {category_url}: {e}")
                continue

            while True:

                soup = BeautifulSoup(html, "html.parser")
                docs = self.extract_documents(soup, category_name)

                self.info(
                    f"Page {self.current_page} : {len(docs)} documents"
                )

                for doc in docs:

                    pdf_url = doc["pdf_url"]

                    if pdf_url in self.visited_pdf_urls:
                        continue

                    self.visited_pdf_urls.add(pdf_url)
                    self.documents.append(doc)

                if self.current_page >= self.max_pages:
                    break

                next_url = self.build_next_page_url(html)

                if next_url is None:
                    break

                self.current_page += 1
                self.info(f"Moving to Page {self.current_page}")

                try:
                    html = self.fetch_page(next_url)
                except Exception as e:
                    self.warning(f"Failed to fetch {next_url}: {e}")
                    break

                time.sleep(self.sleep)

        self.info(
            f"Finished scraping. Total documents : {len(self.documents)}"
        )

        return self.documents

    ##################################################################
    # FETCH PAGE
    ##################################################################

    def fetch_page(self, url):

        self.info(f"GET {url}")
        response = self.get(url)
        return response.text

    ##################################################################
    # EXTRACT DOCUMENTS
    ##################################################################

    def extract_documents(self, soup, category):

        documents = []

        # Find the document table
        table = soup.find("table", id="documents-table")

        if table is None:
            table = soup.find("table", class_="data-table-1")
        
        if table is None:
            table = soup.find("table", class_="doc-table")

        if table is None:
            self.warning("Document table not found.")
            return documents

        rows = table.find_all("tr")

        if len(rows) < 2:
            self.warning("Table has no data rows.")
            return documents

        # Determine column indices from header
        header_row = rows[0]
        headers = [h.get_text(" ", strip=True).lower() for h in header_row.find_all(["th", "td"])]
        
        title_idx = 0
        date_idx = 1
        link_idx = 2
        
        for i, h in enumerate(headers):
            h_lower = h.lower()
            if "title" in h_lower:
                title_idx = i
            elif "date" in h_lower:
                date_idx = i
            elif "view" in h_lower or "download" in h_lower:
                link_idx = i

        # Process data rows (skip header)
        for row in rows[1:]:

            cols = row.find_all("td")

            if len(cols) < 3:
                continue

            try:

                # Get title
                title_col = cols[title_idx] if title_idx < len(cols) else None
                title = title_col.get_text(" ", strip=True) if title_col else ""

                if not title:
                    continue

                # Get date
                date_col = cols[date_idx] if date_idx < len(cols) else None
                date = date_col.get_text(" ", strip=True) if date_col else ""

                # Get PDF URL
                link_col = cols[link_idx] if link_idx < len(cols) else None

                if link_col is None:
                    continue

                link = link_col.find("a")

                if link is None:
                    continue

                href = link.get("href")

                if not href:
                    continue

                # Build full PDF URL (handle relative paths)
                pdf_url = urljoin(self.base_url, href)

                # Ensure it's a PDF
                if not pdf_url.lower().endswith(".pdf"):
                    # Check if link text suggests PDF
                    if "view" in link.get_text(" ", strip=True).lower():
                        # Try to get the PDF URL from onclick or other attributes
                        onclick = link.get("onclick", "")
                        if "pdf" in onclick.lower():
                            # Extract PDF URL from onclick
                            pdf_match = re.search(r"'(https?://[^']+\.pdf)'", onclick)
                            if pdf_match:
                                pdf_url = pdf_match.group(1)
                        else:
                            continue
                    else:
                        continue

                # Get size from link text
                size = ""
                size_match = re.search(r'\(([\d.]+)\s*(MB|KB)\)', link_col.get_text())
                if size_match:
                    size = f"{size_match.group(1)} {size_match.group(2)}"

                # Determine language
                language = self.detect_language(title, pdf_url)

                documents.append({
                    "department": "Housing Department",
                    "category": category,
                    "title": title,
                    "date": date,
                    "language": language,
                    "size": size,
                    "pdf_url": pdf_url,
                    "local_path": "",
                    "sha256": "",
                    "source_page": self.documents_url,
                })

            except Exception as e:
                self.warning(f"Error parsing row: {e}")

        self.info(f"Extracted {len(documents)} documents")

        return documents

    ##################################################################
    # DETECT LANGUAGE
    ##################################################################

    def detect_language(self, title, pdf_url):

        # Check URL
        url_lower = pdf_url.lower()
        if "english" in url_lower or "eng" in url_lower:
            return "English"
        if "marathi" in url_lower or "mar" in url_lower:
            return "Marathi"

        # Check title for Marathi
        marathi_indicators = [
            "अधिनियम", "नियम", "परिपत्र", "सूचना", "गृह",
            "गृहनिर्माण", "झोपडपट्टी", "पुनर्विकास", "भाडे",
            "मालकी", "महाडा", "स्लम", "नियमावली"
        ]
        
        for indicator in marathi_indicators:
            if indicator in title:
                return "Marathi"

        # Check if title has English characters
        if any(c.isalpha() for c in title) and not any(ord(c) > 127 for c in title):
            return "English"

        return "Unknown"

    ##################################################################
    # BUILD NEXT PAGE URL
    ##################################################################

    def build_next_page_url(self, html):

        soup = BeautifulSoup(html, "html.parser")

        # Look for "Next" link
        for a in soup.find_all("a"):
            text = a.get_text(" ", strip=True).lower()
            href = a.get("href")

            if not href:
                continue

            if "next" in text or "→" in text or "»" in text:
                return urljoin(self.base_url, href)

            if text.isdigit():
                page_num = int(text)
                if page_num == self.current_page + 1:
                    return urljoin(self.base_url, href)

        # Build next page URL manually (WordPress pattern)
        current_url = self.current_category_url.rstrip("/")

        if f"/page/{self.current_page}" in current_url:
            next_url = re.sub(
                r"/page/\d+",
                f"/page/{self.current_page + 1}",
                current_url
            )
        else:
            next_url = f"{current_url}/page/{self.current_page + 1}"

        if not next_url.endswith("/"):
            next_url += "/"

        return next_url

    ##################################################################
    # HOUSING SOCIETY RELEVANCE FILTER
    ##################################################################

    def is_relevant(self, document):
        """
        Strict housing relevance filter - keeps housing department documents.
        """
        
        text = (
            document["category"] + " " + 
            document["title"] + " " + 
            document.get("department", "")
        ).lower()

        # Must contain at least ONE housing keyword
        has_housing_keyword = False
        for keyword in self.housing_keywords:
            if keyword in text:
                has_housing_keyword = True
                break

        if not has_housing_keyword:
            return False

        # Must NOT contain any exclusion keywords
        for keyword in self.exclude_keywords:
            if keyword in text:
                return False

        # Skip if title is too short
        title = document["title"].strip()
        if len(title) < 10:
            return False

        return True

    ##################################################################
    # BUILD FILENAME
    ##################################################################

    def build_filename(self, document):

        title = document["title"]
        filename = self.sanitize_filename(title)
        filename = re.sub(r"[^\w\s-]", "", filename)
        filename = re.sub(r"\s+", "_", filename)
        filename = filename[:50]

        date = document.get("date", "")
        if date:
            date_clean = re.sub(r"[^\w\s-]", "_", date)
            date_clean = re.sub(r"\s+", "_", date_clean)
            filename = f"{filename}_{date_clean}"

        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"

        return filename

    ##################################################################
    # DETECT DOCUMENT TYPE
    ##################################################################

    def _detect_document_type(self, title: str) -> str:
        """Detect document type from title."""
        title_lower = title.lower()
        
        type_patterns = {
            "Act": ["act", "अधिनियम"],
            "Rule": ["rule", "rules", "नियम"],
            "Circular": ["circular", "परिपत्रक"],
            "Notification": ["notification", "अधिसूचना"],
            "Guideline": ["guideline", "guidelines", "मार्गदर्शक"],
            "Policy": ["policy", "धोरण"],
            "Minutes": ["minutes", "mom", "meeting", "मिनिटे"],
            "Report": ["report", "अहवाल"],
            "Order": ["order", "आदेश"],
            "Redevelopment": ["redevelopment", "पुनर्विकास"],
            "Slum": ["slum", "झोपडपट्टी"],
            "Rent": ["rent", "भाडे"],
            "Housing": ["housing", "गृहनिर्माण"],
            "MHADA": ["mhada", "महाडा"],
            "RERA": ["rera"],
        }
        
        for doc_type, keywords in type_patterns.items():
            for keyword in keywords:
                if keyword in title_lower:
                    return doc_type
        
        return "Other"

    ##################################################################
    # DOWNLOAD SINGLE DOCUMENT
    ##################################################################

    def download_document(self, document):

        filename = self.build_filename(document)
        self.info(f"Downloading : {filename}")

                # Determine folder
        if self.config.get("storage", {}).get("use_category_storage", False):
            folder = self.get_category_folder(document)
        else:
            folder = "Housing_Department"

        filepath = self.download_pdf(
            pdf_url=document["pdf_url"],
            filename=filename,
            folder=folder
        )

        if filepath is None:
            self.warning("Download failed")
            return False

        sha = self.calculate_sha256(filepath)

        # Extract year from date
        year = ""
        date_str = document.get("date", "")
        if date_str:
            year_match = re.search(r"(\d{4})", date_str)
            if year_match:
                year = year_match.group(1)

        # Extract document type
        doc_type = self._detect_document_type(document.get("title", ""))

        # Create enhanced metadata with ALL required fields
        enhanced_metadata = {
            # Core identification
            "document_id": f"housing_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename[:20]}",
            "title": document.get("title", ""),
            "filename": filename,
            "local_path": str(filepath),
            
            # CRITICAL: Source URLs for chatbot citations
            "pdf_url": document["pdf_url"],
            "source_website": self.source_website,
            "source_page": document.get("source_page", self.documents_url),
            
            # Department & Classification
            "department": self.department,
            "connector": self.name,
            "category": document.get("category", "Unknown"),
            "document_type": doc_type,
            "language": document.get("language", "Unknown"),
            
            # Dates
            "date": document.get("date", ""),
            "gr_date": document.get("date", ""),
            "download_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            
            # Document details
            "unique_code": "",
            "size": str(filepath.stat().st_size),
            "page_count": "",
            "version": "",
            "year": year,
            "sha256": sha,
            
            # Status
            "status": "Downloaded",
            "tags": "",
        }

        self.info(f"Saved Successfully: {filename}")
        self.info(f"Source: {enhanced_metadata['source_website']}")
        
        # Store enhanced metadata on document
        document.update(enhanced_metadata)

        return True

    ##################################################################
    # DOWNLOAD ALL
    ##################################################################

    def download_all(self):

        downloaded = 0
        skipped = 0
        total = len(self.documents)

        self.info("=" * 70)
        self.info(f"Processing {total} documents (Housing Filter)")
        self.info("=" * 70)

        for i, doc in enumerate(self.documents, start=1):

            self.info(f"[{i}/{total}]")

            if not self.is_relevant(doc):
                skipped += 1
                self.info("⏭️  Skipped (Not Housing Related)")
                continue

            success = self.download_document(doc)

            if success:
                downloaded += 1

            time.sleep(self.sleep)

        self.info("=" * 70)
        self.info(f"Downloaded : {downloaded}")
        self.info(f"Skipped    : {skipped}")
        self.info("=" * 70)

        return downloaded

    ##################################################################
    # SAVE METADATA
    ##################################################################

    def save_metadata(self):

        try:
            import csv
            from pathlib import Path

            metadata_dir = Path("metadata")
            metadata_dir.mkdir(exist_ok=True)

            csv_file = metadata_dir / "housing_department_metadata.csv"

            fields = [
                "document_id",
                "title",
                "filename",
                "local_path",
                "pdf_url",
                "source_website",
                "source_page",
                "department",
                "connector",
                "category",
                "document_type",
                "language",
                "date",
                "gr_date",
                "download_date",
                "unique_code",
                "size",
                "page_count",
                "version",
                "year",
                "sha256",
                "status",
                "tags",
            ]

            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()

                for doc in self.documents:
                    if doc.get("status") == "Downloaded":
                        writer.writerow({
                            "document_id": doc.get("document_id", ""),
                            "title": doc.get("title", ""),
                            "filename": doc.get("filename", ""),
                            "local_path": doc.get("local_path", ""),
                            "pdf_url": doc.get("pdf_url", ""),
                            "source_website": doc.get("source_website", ""),
                            "source_page": doc.get("source_page", ""),
                            "department": doc.get("department", ""),
                            "connector": doc.get("connector", ""),
                            "category": doc.get("category", ""),
                            "document_type": doc.get("document_type", ""),
                            "language": doc.get("language", ""),
                            "date": doc.get("date", ""),
                            "gr_date": doc.get("gr_date", ""),
                            "download_date": doc.get("download_date", ""),
                            "unique_code": doc.get("unique_code", ""),
                            "size": doc.get("size", ""),
                            "page_count": doc.get("page_count", ""),
                            "version": doc.get("version", ""),
                            "year": doc.get("year", ""),
                            "sha256": doc.get("sha256", ""),
                            "status": doc.get("status", ""),
                            "tags": doc.get("tags", ""),
                        })

            self.info(f"Metadata saved -> {csv_file}")

        except Exception as e:
            self.error(f"Metadata Error : {e}")

    ##################################################################
    # RUN
    ##################################################################

    def run(self):

        start = time.time()

        self.info("=" * 80)
        self.info("Housing Department Started (Housing Focus)")
        self.info("=" * 80)

        try:

            self.scrape()

            if len(self.documents) == 0:
                self.warning("No documents found.")
                return []

            self.info(
                f"Documents discovered : {len(self.documents)}"
            )

            downloaded = self.download_all()

            self.save_metadata()

            self.info("=" * 80)
            self.info("SCRAPER FINISHED")
            self.info(f"Categories Crawled : {len(self.category_urls)}")
            self.info(f"Documents Found : {len(self.documents)}")
            self.info(f"Documents Downloaded : {downloaded}")
            self.info(
                f"Execution Time : "
                f"{round(time.time()-start,2)} sec"
            )
            self.info("=" * 80)

            return self.documents

        except Exception as e:
            self.error(str(e))
            raise

    ##################################################################
    # FRAMEWORK ENTRY
    ##################################################################

    def execute(self):
        return self.run()