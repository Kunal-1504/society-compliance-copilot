"""
Cooperation Department Connector

Scrapes:
https://mahasahakar.maharashtra.gov.in/en/documents/

Housing Society Focused Connector
Only downloads documents relevant to housing societies.
"""

import re
import time
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from core.base_connector import BaseConnector


class CooperationConnector(BaseConnector):

    def __init__(self, config, logger):

        super().__init__(config)

        self.logger = logger
        self.config = config

        self.name = "Cooperation Department"
        self.source_website = "https://mahasahakar.maharashtra.gov.in"
        self.department = "Cooperation Department"

        self.base_url = config["cooperation"]["base_url"]
        self.documents_url = config["cooperation"]["documents_url"]

        self.category_urls = {
            "Acts & Rules": f"{self.base_url}/en/document-category/acts-rules/",
            "Government Resolution / Notification": f"{self.base_url}/en/document-category/government-resolution-notification/",
            "Circular": f"{self.base_url}/en/document-category/circular/",
            "Registrar Circular": f"{self.base_url}/en/document-category/registrar-circular/",
            "Audit": f"{self.base_url}/en/document-category/audit/",
            "Audit Guidelines": f"{self.base_url}/en/document-category/audit-guidelines/",
            "Housing Society Circulars": f"{self.base_url}/en/document-category/housing-society-circulars/",
            "Model Bye-laws": f"{self.base_url}/en/document-category/model-bye-laws/",
            "Redevelopment": f"{self.base_url}/en/document-category/redevelopment/",
            "Deemed Conveyance": f"{self.base_url}/en/document-category/deemed-conveyance/",
            "Election": f"{self.base_url}/en/document-category/election/",
            "Annual Return": f"{self.base_url}/en/document-category/annual-return/",
            "AGM": f"{self.base_url}/en/document-category/agm/"
        }

        self.max_pages = config["cooperation"].get("max_pages", 50)
        self.sleep = config["cooperation"].get("delay", 2)

        self.current_page = 1
        self.current_category = ""
        self.current_category_url = ""

        self.documents = []
        self.visited_pdf_urls = set()
        self.downloaded_docs = []  # NEW: Track downloaded docs

        # Housing Society Focused Keywords
        self.housing_keywords = {
            # Core housing society terms
            "housing society",
            "cooperative housing",
            "co-operative housing",
            "housing society redevelopment",
            "society redevelopment",
            "redevelopment of buildings",
            "redevelopment of cooperative",
            "redevelopment of housing",
            
            # Conveyance related
            "deemed conveyance",
            "conveyance",
            "transfer of title",
            "title transfer",
            
            # Building/Society specific
            "building",
            "dilapidated",
            "cessed building",
            "old building",
            "reconstruction",
            "re-construction",
            
            # Society management
            "cooperative societies act",
            "cooperative societies rules",
            "committee election",
            "society election",
            "society audit",
            "audit fees",
            "bye-law",
            "byelaw",
            "model bye-laws",
            
            # Society operations
            "society circular",
            "housing society circular",
            "registrar circular",
            "society registration",
            "society member",
            "share holding",
            "society share",
            
            # Specific acts/rules
            "mcs act",
            "maharashtra cooperative societies act",
            "maharashtra co-operative societies act",
            "maharashtra housing",
            
            # Marathi housing terms
            "गृहनिर्माण",
            "गृह",
            "सहकारी संस्था",
            "सहकार गृहनिर्माण",
            "सोसायटी",
            "पुनर्विकास",
            "अभिहस्तांतरण",
            "विकास",
            "इमारत",
            "जुनी इमारत",
            
            # Related topics
            "auditor panel",
            "auditor empanelment",
            "society auditor",
            "cooperative awards",
            "co-operation policy"
        }

        # Keywords to EXCLUDE (non-housing)
        self.exclude_keywords = [
            "agriculture",
            "crop loan",
            "kharif",
            "money lending",
            "money lender",
            "promotion",
            "seniority",
            "transfer by counselling",
            "career progression",
            "reservation for specially abled",
            "reservation in promotion",
            "staff",
            "employee",
            "government employee",
            "agricultural",
            "sugar",
            "pacs",
            "marketing",
            "rural development",
            "tribal",
            "fisheries",
            "animal husbandry",
            "poultry",
            "dairy",
            "taluka-level committee",
            "district cooperative",
            "state cooperative",
            "administrative report",
            "budget",
            "office order",
            "tender",
            "recruitment",
            "विभागीय",
            "कृषी",
            "साखर",
            "दूध",
            "मत्स्य",
            "प्रशासनिक"
        ]

    ##################################################################
    # MAIN ENTRY
    ##################################################################

    def scrape(self):

        self.info("=" * 70)
        self.info("Cooperation Department - Housing Society Focus")
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

        table = soup.find("table")

        if table is None:
            self.warning("Document table not found.")
            return documents

        rows = table.find_all("tr")

        # Find column indices
        header_row = rows[0] if rows else None
        title_idx = 0
        date_idx = 1
        link_idx = 2

        if header_row:
            headers = [th.get_text(" ", strip=True).lower() for th in header_row.find_all(["th", "td"])]
            for i, h in enumerate(headers):
                if "title" in h:
                    title_idx = i
                elif "date" in h:
                    date_idx = i
                elif "view" in h or "download" in h:
                    link_idx = i

        for row in rows[1:]:

            cols = row.find_all("td")

            if len(cols) < 3:
                continue

            try:

                title_col = cols[title_idx] if title_idx < len(cols) else None
                title = title_col.get_text(" ", strip=True) if title_col else ""

                if not title:
                    continue

                date_col = cols[date_idx] if date_idx < len(cols) else None
                date = date_col.get_text(" ", strip=True) if date_col else ""

                link_col = cols[link_idx] if link_idx < len(cols) else None

                if link_col is None:
                    continue

                link = link_col.find("a")

                if link is None:
                    continue

                href = link.get("href")

                if not href:
                    continue

                pdf_url = urljoin(self.base_url, href)

                if not pdf_url.lower().endswith(".pdf"):
                    continue

                # Determine language
                language = "Unknown"
                if "english" in pdf_url.lower() or "en" in pdf_url.lower():
                    language = "English"
                elif "marathi" in pdf_url.lower() or "mr" in pdf_url.lower():
                    language = "Marathi"

                if language == "Unknown":
                    title_lower = title.lower()
                    if any(word in title_lower for word in ["english", "en"]):
                        language = "English"
                    elif any(word in title_lower for word in ["marathi", "mr"]):
                        language = "Marathi"

                documents.append({
                    "department": "Cooperation Department",
                    "category": category,
                    "title": title,
                    "date": date,
                    "language": language,
                    "size": "",
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
                return href

            if text.isdigit():
                page_num = int(text)
                if page_num == self.current_page + 1:
                    return href

        # Build next page URL manually
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
        Strict housing society relevance filter.
        Only returns True for documents directly related to housing societies.
        """
        
        # Combine all text for checking
        text = (
            document["category"] + " " + 
            document["title"] + " " + 
            document.get("department", "")
        ).lower()

        # First check: Must contain at least ONE housing society keyword
        has_housing_keyword = False
        for keyword in self.housing_keywords:
            if keyword in text:
                has_housing_keyword = True
                break

        if not has_housing_keyword:
            return False

        # Second check: Must NOT contain any exclusion keywords
        for keyword in self.exclude_keywords:
            if keyword in text:
                return False

        # Additional check: If title is extremely short or generic, skip
        title = document["title"].strip()
        if len(title) < 10:
            return False

        # Additional check: Skip if it's purely about government employees
        employee_terms = ["promotion", "seniority", "transfer", "counselling", 
                         "career progression", "staff", "employee"]
        if any(term in text for term in employee_terms):
            # But keep if it also has housing keywords
            housing_in_employee_doc = any(
                keyword in text for keyword in [
                    "housing society", "cooperative housing", "society redevelopment"
                ]
            )
            if not housing_in_employee_doc:
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
            "Bye-law": ["bye-law", "byelaw", "by law", "उपविधी"],
            "Circular": ["circular", "परिपत्रक"],
            "Notification": ["notification", "अधिसूचना"],
            "Guideline": ["guideline", "guidelines", "मार्गदर्शक"],
            "Policy": ["policy", "धोरण"],
            "Election": ["election", "निवडणूक"],
            "Audit": ["audit", "लेखापरीक्षण"],
            "Redevelopment": ["redevelopment", "पुनर्विकास"],
            "Conveyance": ["conveyance", "अभिहस्तांतरण"],
            "Government Resolution": ["gr", "government resolution", "शासन निर्णय"],
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
            folder = "Cooperation_Department"

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

        # Get classified category
        classified_category = ""
        if self.config.get("storage", {}).get("use_category_storage", False):
            try:
                classified_category = self.get_category_folder(document)
            except Exception as e:
                self.warning(f"Failed to get classified category: {e}")

        # Create enhanced metadata with ALL required fields
        enhanced_metadata = {
            # Core identification
            "document_id": f"coop_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename[:20]}",
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
            "classified_category": classified_category,
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
            "connector_folder": folder,
            "classification_confidence": "",
            "classification_reason": "",
            "matched_keywords": "",
            "schema_version": "1.1",
        }

        self.info(f"Saved Successfully: {filename} to {folder}/")
        self.info(f"Source: {enhanced_metadata['source_website']}")
        
        # Store enhanced metadata on document
        document.update(enhanced_metadata)

        return True

    ##################################################################
    # DOWNLOAD ALL - FIXED: Track downloaded documents
    ##################################################################

    def download_all(self):

        downloaded = 0
        skipped = 0
        total = len(self.documents)

        self.info("=" * 70)
        self.info(f"Processing {total} documents (Housing Society Filter)")
        self.info("=" * 70)

        # Clear previously downloaded list
        self.downloaded_docs = []

        for i, doc in enumerate(self.documents, start=1):

            self.info(f"[{i}/{total}]")

            if not self.is_relevant(doc):
                skipped += 1
                self.info("⏭️  Skipped (Not Housing Society Related)")
                continue

            success = self.download_document(doc)

            if success:
                downloaded += 1
                # FIX: Add to downloaded_docs list
                self.downloaded_docs.append(doc)
                self.info(f"Added to downloaded docs (total: {len(self.downloaded_docs)})")

            time.sleep(self.sleep)

        self.info("=" * 70)
        self.info(f"Downloaded : {downloaded}")
        self.info(f"Skipped    : {skipped}")
        self.info("=" * 70)

        return downloaded

    ##################################################################
    # SAVE METADATA - FIXED: Only save downloaded documents
    ##################################################################

    def save_metadata(self):

        try:
            import csv
            from pathlib import Path

            metadata_dir = Path("metadata")
            metadata_dir.mkdir(exist_ok=True)

            csv_file = metadata_dir / "cooperation_department_metadata.csv"

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
                "classified_category",
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
                "connector_folder",
                "classification_confidence",
                "classification_reason",
                "matched_keywords",
                "schema_version",
            ]

            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()

                # FIX: Only write downloaded documents
                downloaded_count = 0
                for doc in self.documents:
                    if doc.get("status") == "Downloaded":
                        downloaded_count += 1
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
                            "classified_category": doc.get("classified_category", ""),
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
                            "connector_folder": doc.get("connector_folder", ""),
                            "classification_confidence": doc.get("classification_confidence", ""),
                            "classification_reason": doc.get("classification_reason", ""),
                            "matched_keywords": doc.get("matched_keywords", ""),
                            "schema_version": doc.get("schema_version", ""),
                        })

                self.info(f"Saved {downloaded_count} downloaded documents to {csv_file}")
                self.info(f"Metadata saved -> {csv_file}")

        except Exception as e:
            self.error(f"Metadata Error : {e}")

    ##################################################################
    # RUN - FIXED: Return downloaded documents
    ##################################################################

    def run(self):

        start = time.time()

        self.info("=" * 80)
        self.info("Cooperation Department Started (Housing Society Focus)")
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

            # FIX: Return downloaded documents, not all scraped documents
            self.info(f"Returning {len(self.downloaded_docs)} downloaded documents")
            return self.downloaded_docs

        except Exception as e:
            self.error(str(e))
            raise

    ##################################################################
    # FRAMEWORK ENTRY
    ##################################################################

    def execute(self):
        return self.run()