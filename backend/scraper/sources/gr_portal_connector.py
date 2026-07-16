"""
Government Resolution Portal Connector

Scrapes:
https://gr.maharashtra.gov.in/1145/Government-Resolutions

Supports

✓ ASP.NET ViewState
✓ Pagination
✓ Hidden fields
✓ Metadata extraction
✓ PDF download
✓ Duplicate skipping
✓ Scoring-based relevance filtering for Cooperative Housing Societies
"""

import re
import time
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from core.base_connector import BaseConnector


class GRPortalConnector(BaseConnector):

    def __init__(self, config, logger):

        super().__init__(config)

        self.logger = logger
        self.config = config

        self.name = "Government Resolution Portal"
        self.source_website = "https://gr.maharashtra.gov.in"
        self.department = "General Administration Department"
        self.connector_name = "GR Portal"

        self.base_url = config["gr_portal"]["base_url"]

        self.max_pages = config["gr_portal"].get("max_pages", 50)
        self.sleep = config["gr_portal"].get("delay", 2)

        self.current_page = 1
        self.hidden_fields = {}
        self.documents = []   
        self.visited_codes = set()
        self.downloaded_docs = []

        # Scoring configuration
        gr_config = config.get("gr_portal", {})
        self.relevance_threshold = gr_config.get("relevance_threshold", 3.0)

        self.logger.info(f"Relevance threshold: {self.relevance_threshold}")

    ##################################################################
    # MAIN ENTRY
    ##################################################################

    def scrape(self):

        self.info("=" * 70)
        self.info("Government Resolution Portal")
        self.info("=" * 70)

        html = self.fetch_first_page()

        while True:

            soup = BeautifulSoup(html, "html.parser")

            self.extract_hidden_fields(soup)

            docs = self.extract_documents(soup)

            self.info(
                f"Page {self.current_page} : {len(docs)} documents"
            )

            for doc in docs:

                code = doc["unique_code"]

                if code in self.visited_codes:
                    continue

                self.visited_codes.add(code)

                # Add source metadata
                doc["source_page"] = self.base_url
                doc["source_website"] = self.source_website
                doc["connector"] = self.connector_name
                doc["department"] = doc.get("department", self.department)

                self.documents.append(doc)

            if self.current_page >= self.max_pages:
                break

            if not self.has_next_page(soup):
                break

            self.current_page += 1

            self.info(f"Moving to Page {self.current_page}")

            html = self.goto_next_page()

            time.sleep(self.sleep)

        self.info(
            f"Finished scraping. Total documents : {len(self.documents)}"
        )

        return self.documents

    ##################################################################
    # FETCH FIRST PAGE
    ##################################################################

    def fetch_first_page(self):

        self.info("Loading first page")

        response = self.get(self.base_url)

        return response.text

    ##################################################################
    # EXTRACT ASP.NET HIDDEN FIELDS
    ##################################################################

    def extract_hidden_fields(self, soup):

        self.hidden_fields = {}

        hidden = soup.find_all("input", type="hidden")

        for field in hidden:

            name = field.get("name")

            value = field.get("value", "")

            if name:
                self.hidden_fields[name] = value

        self.info(
            f"Hidden fields : {len(self.hidden_fields)}"
        )

    ##################################################################
    # FIND NEXT PAGE
    ##################################################################

    def has_next_page(self, soup):

        target = f"ctl00$SitePH$ucPaging$p{self.current_page+1}"

        for a in soup.find_all("a"):

            href = a.get("href", "")

            if target in href:
                return True

        return False

    ##################################################################
    # GOTO NEXT PAGE
    ##################################################################

    def goto_next_page(self):

        event_target = f"ctl00$SitePH$ucPaging$p{self.current_page}"

        payload = dict(self.hidden_fields)

        payload["__EVENTTARGET"] = event_target
        payload["__EVENTARGUMENT"] = ""
        payload["__LASTFOCUS"] = ""

        self.info(f"POST -> Page {self.current_page}")

        response = self.post(self.base_url, payload)

        return response.text

    ##################################################################
    # FIND THE GR TABLE
    ##################################################################

    def find_gr_table(self, soup):

        tables = soup.find_all("table")

        for table in tables:

            text = table.get_text(" ", strip=True)

            if (
                "Department Name" in text
                and "Unique Code" in text
                and "G.R. Date" in text
            ):
                return table

            if (
                "विभागाचे नाव" in text
                and "युनिक क्रमांक" in text
            ):
                return table

        return None

    ##################################################################
    # EXTRACT DOCUMENTS
    ##################################################################

    def extract_documents(self, soup):
        """
        Parse the GR table correctly.
        """

        documents = []

        table = soup.find("table", id="SitePH_dgvDocuments")

        if table is None:
            self.warning("GR table not found.")
            return documents

        rows = table.find_all("tr")[1:]   # Skip header

        self.info(f"Found {len(rows)} table rows")

        for row in rows:

            cols = row.find_all("td")

            if len(cols) != 7:
                continue

            try:

                department = cols[1].get_text(" ", strip=True)

                title = cols[2].get_text(" ", strip=True)

                code = cols[3].get_text(" ", strip=True)

                date = cols[4].get_text(" ", strip=True)

                size = cols[5].get_text(" ", strip=True)

                link = cols[6].find("a")

                if link is None:
                    continue

                href = link.get("href")

                if not href:
                    continue

                pdf_url = urljoin(self.base_url, href)

                language = "Marathi"

                if "/English/" in pdf_url:
                    language = "English"

                documents.append({

                    "department": department,

                    "title": title,

                    "unique_code": code,

                    "date": date,

                    "size": size,

                    "language": language,

                    "pdf_url": pdf_url,

                    "source_page": self.base_url,

                })

            except Exception as e:

                self.warning(e)

        self.info(f"Extracted {len(documents)} documents")

        return documents

    ##################################################################
    # IMPROVED RELEVANCE SCORING FOR HOUSING SOCIETIES
    ##################################################################

    def _calculate_relevance_score(self, document):
        """
        Calculate relevance score for Cooperative Housing Society documents.
        Returns score and matched keywords.
        """
        # Combine all text for analysis
        text = (
            document.get("department", "") + " " +
            document.get("title", "")
        ).lower()

        # Remove extra spaces
        text = re.sub(r"\s+", " ", text).strip()

        # --- POSITIVE KEYWORDS (Housing Society Related) ---
        positive_keywords = {
            # Highest weight (3.0) - Direct housing society terms
            "cooperative housing society": 3.0,
            "co-operative housing society": 3.0,
            "cooperative housing": 3.0,
            "co-operative housing": 3.0,
            "housing society": 3.0,
            "गृहनिर्माण संस्था": 3.0,
            "सहकारी गृहनिर्माण": 3.0,
            "सहकारी गृहनिर्माण संस्था": 3.0,

            # High weight (2.5) - Core housing terms
            "housing": 2.5,
            "गृहनिर्माण": 2.5,
            "cooperative": 2.5,
            "co-operative": 2.5,
            "सहकारी": 2.5,
            "society": 2.5,
            "संस्था": 2.5,

            # Medium-high weight (2.0) - Specific topics
            "redevelopment": 2.0,
            "पुनर्विकास": 2.0,
            "deemed conveyance": 2.0,
            "conveyance": 2.0,
            "अभिहस्तांतरण": 2.0,
            "mcs act": 2.0,
            "maharashtra cooperative societies act": 2.0,
            "maharashtra co-operative societies act": 2.0,
            "model bye-laws": 2.0,
            "model byelaws": 2.0,
            "bye-law": 2.0,
            "byelaw": 2.0,
            "आदर्श उपविधी": 2.0,
            "उपनियम": 2.0,

            # Medium weight (1.5) - Management topics
            "election": 1.5,
            "निवडणूक": 1.5,
            "audit": 1.5,
            "लेखापरीक्षण": 1.5,
            "committee": 1.5,
            "समिती": 1.5,
            "agm": 1.5,
            "annual general meeting": 1.5,
            "वार्षिक सभा": 1.5,
            "member": 1.5,
            "registrar": 1.5,
            "निबंधक": 1.5,
            "mofa": 1.5,
            "mhada": 1.5,
            "maharashtra housing": 1.5,
            "apartment ownership": 1.5,
            "ownership flats": 1.5,
            "flat": 1.5,
            "apartment": 1.5,
            "housing federation": 1.5,
            "society registration": 1.5,

            # Lower weight (1.0) - Related terms
            "circular": 1.0,
            "notification": 1.0,
            "हाऊसिंग": 1.0,
            "सोसायटी": 1.0,
        }

        # --- NEGATIVE KEYWORDS (To reject) ---
        negative_keywords = {
            "agriculture": 4.0,
            "agricultural": 4.0,
            "कृषी": 4.0,
            "farm": 4.0,
            "livestock": 4.0,
            "fisheries": 4.0,
            "employment": 4.0,
            "रोजगार": 4.0,
            "tourism": 4.0,
            "पर्यटन": 4.0,
            "police": 4.0,
            "पोलीस": 4.0,
            "road": 4.0,
            "highway": 4.0,
            "bridge": 4.0,
            "रस्ता": 4.0,
            "water supply": 4.0,
            "पाणीपुरवठा": 4.0,
            "irrigation": 4.0,
            "सिंचन": 4.0,
            "forest": 4.0,
            "वन": 4.0,
            "health": 4.0,
            "medical": 4.0,
            "hospital": 4.0,
            "आरोग्य": 4.0,
            "education": 4.0,
            "university": 4.0,
            "school": 4.0,
            "शिक्षण": 4.0,
            "transport": 4.0,
            "वाहतूक": 4.0,
            "railway": 4.0,
            "metro": 4.0,
            "industry": 4.0,
            "उद्योग": 4.0,
            "msme": 4.0,
            "skill development": 4.0,
            "recruitment": 4.0,
            "भरती": 4.0,
            "pension": 4.0,
            "निवृत्तिवेतन": 4.0,
            "social welfare": 4.0,
            "women and child": 4.0,
            "rural development": 4.0,
            "ग्रामीण विकास": 4.0,
        }

        # Calculate score
        score = 0.0
        matched_positive = []
        matched_negative = []

        # Check positive keywords
        for keyword, weight in positive_keywords.items():
            if keyword in text:
                score += weight
                matched_positive.append(keyword)

        # Check negative keywords
        for keyword, weight in negative_keywords.items():
            if keyword in text:
                score -= weight
                matched_negative.append(keyword)

        return {
            "score": score,
            "matched_positive": matched_positive,
            "matched_negative": matched_negative,
            "text_preview": text[:100] + "..." if len(text) > 100 else text
        }

    ##################################################################
    # IS RELEVANT - MAIN FILTERING LOGIC
    ##################################################################

    def is_relevant(self, document):
        """
        Determine if a GR is relevant to Cooperative Housing Societies.
        Uses scoring system with positive and negative keywords.
        Only downloads if score >= threshold (default: 3.0).
        """
        result = self._calculate_relevance_score(document)
        score = result["score"]
        matched_positive = result["matched_positive"]
        matched_negative = result["matched_negative"]

        # Log what was found
        title_preview = document.get("title", "")[:60] + "..." if len(document.get("title", "")) > 60 else document.get("title", "")

        if matched_positive:
            self.info(f"  ✓ Matched positive: {', '.join(matched_positive[:3])}")
        if matched_negative:
            self.info(f"  ✗ Matched negative: {', '.join(matched_negative[:3])}")

        self.info(f"  Score: {score:.1f} (threshold: {self.relevance_threshold})")

        # Decision: relevant if score meets threshold
        is_relevant = score >= self.relevance_threshold

        if is_relevant:
            self.info(f"  ✅ RELEVANT: {title_preview}")
        else:
            self.info(f"  ❌ SKIPPED: {title_preview}")

        return is_relevant

    ##################################################################
    # BUILD FILENAME
    ##################################################################

    def build_filename(self, document):
        title = self.sanitize_filename(document["title"])

        # Remove special characters
        title = re.sub(r"[^\w\s-]", "", title)

        # Replace spaces with underscores
        title = re.sub(r"\s+", "_", title)

        # Limit title length
        title = title[:40]

        # Clean unique code
        code = document["unique_code"].replace("...", "")

        filename = f"{code}_{title}.pdf"

        return filename

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
            folder = "Government_Resolutions"

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
            "document_id": f"gr_{document.get('unique_code', '')}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "title": document.get("title", ""),
            "filename": filename,
            "local_path": str(filepath),
            
            "pdf_url": document["pdf_url"],
            "source_website": self.source_website,
            "source_page": document.get("source_page", self.base_url),
            
            "department": document.get("department", self.department),
            "connector": self.connector_name,
            "category": "Government Resolution",
            "classified_category": classified_category,
            "document_type": doc_type,
            "language": document.get("language", "Unknown"),
            
            "date": document.get("date", ""),
            "gr_date": document.get("date", ""),
            "download_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            
            "unique_code": document.get("unique_code", ""),
            "size": str(filepath.stat().st_size),
            "page_count": "",
            "version": "",
            "year": year,
            "sha256": sha,
            
            "status": "Downloaded",
            "tags": "",
            "connector_folder": folder,
            "classification_confidence": "",
            "classification_reason": "",
            "matched_keywords": "",
            "schema_version": "1.1",
        }

        self.info(f"✅ Saved Successfully: {filename} to {folder}/")
        self.info(f"Source: {enhanced_metadata['source_website']}")
        
        # Store enhanced metadata on document
        document.update(enhanced_metadata)

        return True

    ##################################################################
    # DETECT DOCUMENT TYPE
    ##################################################################

    def _detect_document_type(self, title: str) -> str:
        """Detect document type from title."""
        title_lower = title.lower()
        
        type_patterns = {
            "Government Resolution": ["gr", "government resolution", "शासन निर्णय"],
            "Notification": ["notification", "अधिसूचना"],
            "Circular": ["circular", "परिपत्रक"],
            "Order": ["order", "आदेश"],
            "Policy": ["policy", "धोरण"],
            "Guideline": ["guideline", "guidelines", "मार्गदर्शक"],
            "Amendment": ["amendment", "सुधारणा"],
            "Act": ["act", "अधिनियम"],
            "Rule": ["rule", "rules", "नियम"],
        }
        
        for doc_type, keywords in type_patterns.items():
            for keyword in keywords:
                if keyword in title_lower:
                    return doc_type
        
        return "Government Resolution"

    ##################################################################
    # DOWNLOAD ALL
    ##################################################################

    def download_all(self):

        downloaded = 0
        skipped = 0
        total = len(self.documents)

        self.info("=" * 70)
        self.info(f"Processing {total} documents (Housing Society Score >= {self.relevance_threshold})")
        self.info("=" * 70)

        # Clear previously downloaded list
        self.downloaded_docs = []

        for i, doc in enumerate(self.documents, start=1):

            self.info(f"[{i}/{total}]")

            # Check relevance using improved scoring
            if not self.is_relevant(doc):
                skipped += 1
                self.info("Skipped (Not Housing Society Related)")
                continue

            success = self.download_document(doc)

            if success:
                downloaded += 1
                self.downloaded_docs.append(doc)
                self.info(f"Added to downloaded docs (total: {len(self.downloaded_docs)})")

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

            csv_file = metadata_dir / "gr_portal_metadata.csv"

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

                writer = csv.DictWriter(
                    f,
                    fieldnames=fields,
                    extrasaction='ignore'
                )

                writer.writeheader()

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

                self.info(f"✅ Saved {downloaded_count} downloaded documents to {csv_file}")

        except Exception as e:

            self.error(f"Metadata Error : {e}")

    ##################################################################
    # RUN
    ##################################################################

    def run(self):

        start = time.time()

        self.info("=" * 80)
        self.info("Government Resolution Portal Started")
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

            self.info(f"Pages Crawled : {self.current_page}")

            self.info(f"Documents Found : {len(self.documents)}")

            self.info(f"Documents Downloaded : {downloaded}")

            self.info(
                f"Execution Time : "
                f"{round(time.time()-start,2)} sec"
            )

            self.info("=" * 80)

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