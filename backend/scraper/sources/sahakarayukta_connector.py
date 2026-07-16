"""
Sahakarayukta (Registrar of Cooperative Societies) Connector

Scrapes:
https://sahakarayukta.maharashtra.gov.in/

Sections:
- Acts & Rules
- GR / Circulars / Notifications
- Model Bye Laws
- Schemes
- RTI
- Publication

Housing Society Focused
"""

import re
import time
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from core.base_connector import BaseConnector


class SahakarayuktaConnector(BaseConnector):

    def __init__(self, config, logger):

        super().__init__(config)

        self.logger = logger
        self.config = config

        self.name = "Sahakarayukta (Registrar of Cooperative Societies)"
        self.source_website = "https://sahakarayukta.maharashtra.gov.in"
        self.department = "Commissioner and Registrar of Cooperative Societies"

        self.base_url = config["sahakarayukta"]["base_url"]
        
        # Section URLs
        self.section_urls = {
            "Acts & Rules": f"{self.base_url}/Site/Information/ListingUploadOtherPdf.aspx?Doctype=883C2837-B898-4558-8CD6-87090AD2291B&MenuID=1072",
            "GR / Circulars / Notifications": f"{self.base_url}/1065/GR-/-Circulars-/-Notifications",
            "Model Bye Laws": f"{self.base_url}/1105/Model-Bye-Laws?Doctype=1CC73BAD-36CA-45AA-BA03-2119E31B6337",
            "Schemes": f"{self.base_url}/1066/Schemes",
            "RTI": f"{self.base_url}/1067/RTI",
            "Publication": f"{self.base_url}/1073/Publication?Doctype=6C0E65A7-8EFF-4744-8CE8-0F734FB62FB8",
        }

        self.max_pages = config["sahakarayukta"].get("max_pages", 50)
        self.sleep = config["sahakarayukta"].get("delay", 2)

        self.documents = []
        self.visited_pdf_urls = set()

        # Housing Society Keywords (for relevance filtering)
        self.housing_keywords = [
            # English
            "housing",
            "housing society",
            "cooperative housing",
            "co-operative housing",
            "society redevelopment",
            "redevelopment of buildings",
            "redevelopment of cooperative",
            "deemed conveyance",
            "conveyance",
            "transfer of title",
            "building",
            "dilapidated",
            "cessed building",
            "reconstruction",
            "model bye laws housing",
            "housing rules",
            "गृहनिर्माण",
            "गृह",
            "सहकारी संस्था",
            "सहकार गृहनिर्माण",
            "सोसायटी",
            "पुनर्विकास",
            "अभिहस्तांतरण",
            "इमारत",
            "जुनी इमारत",
            # MCS Act (always relevant)
            "maharashtra cooperative societies act",
            "mcs act",
            "cooperative societies act",
            "cooperative societies rules",
            "committee election",
            "society election",
        ]

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
            "administrative report",
            "budget",
            "office order",
            "tender",
            "recruitment",
            "departmental exam",
            "gdca",
            "gdc&a",
            "विभागीय",
            "कृषी",
            "साखर",
            "दूध",
            "मत्स्य",
            "प्रशासनिक",
        ]

    ##################################################################
    # MAIN ENTRY
    ##################################################################

    def scrape(self):

        self.info("=" * 70)
        self.info("Sahakarayukta - Housing Society Focus")
        self.info("=" * 70)

        for section_name, section_url in self.section_urls.items():

            self.info(f"\n--- Section: {section_name} ---")
            
            if section_name == "GR / Circulars / Notifications":
                # This section has pagination
                self.scrape_gr_section(section_name, section_url)
            else:
                # Single page sections
                self.scrape_single_page(section_name, section_url)

        self.info(
            f"Finished scraping. Total documents : {len(self.documents)}"
        )

        return self.documents

    ##################################################################
    # SCRAPE SINGLE PAGE SECTION
    ##################################################################

    def scrape_single_page(self, section_name, section_url):

        try:
            html = self.fetch_page(section_url)
            soup = BeautifulSoup(html, "html.parser")
            
            # Pass section_url to extract_documents
            docs = self.extract_documents(soup, section_name, section_url)
            
            self.info(f"Found {len(docs)} documents")
            
            for doc in docs:
                pdf_url = doc["pdf_url"]
                if pdf_url not in self.visited_pdf_urls:
                    self.visited_pdf_urls.add(pdf_url)
                    self.documents.append(doc)
                    
        except Exception as e:
            self.warning(f"Failed to scrape {section_name}: {e}")

    ##################################################################
    # SCRAPE GR SECTION (WITH PAGINATION)
    ##################################################################

    def scrape_gr_section(self, section_name, section_url):

        current_page = 1
        current_url = section_url

        while True:

            try:
                html = self.fetch_page(current_url)
                soup = BeautifulSoup(html, "html.parser")
                
                # Pass current_url to extract_documents
                docs = self.extract_documents(soup, section_name, current_url)
                
                self.info(f"Page {current_page}: Found {len(docs)} documents")
                
                for doc in docs:
                    pdf_url = doc["pdf_url"]
                    if pdf_url not in self.visited_pdf_urls:
                        self.visited_pdf_urls.add(pdf_url)
                        self.documents.append(doc)
                
                # Check for next page
                next_url = self.build_next_page_url(soup, current_url)
                
                if next_url is None or current_page >= self.max_pages:
                    break
                
                current_page += 1
                current_url = next_url
                self.info(f"Moving to Page {current_page}")
                time.sleep(self.sleep)
                
            except Exception as e:
                self.warning(f"Failed on page {current_page}: {e}")
                break

    ##################################################################
    # FETCH PAGE
    ##################################################################

    def fetch_page(self, url):

        self.info(f"GET {url}")
        response = self.get(url)
        return response.text

    ##################################################################
    # EXTRACT DOCUMENTS - UPDATED WITH section_url PARAMETER
    ##################################################################

    def extract_documents(self, soup, section_name, section_url):

        documents = []

        # Find the document table
        table = None
        
        # Method 1: Look for table with ID SitePH_grdupload
        table = soup.find("table", id="SitePH_grdupload")
        
        if table is None:
            # Method 2: Look for table with ID SitePH_GridView1 (GR section)
            table = soup.find("table", id="SitePH_GridView1")
        
        if table is None:
            # Method 3: Look for any table with class t_view
            table = soup.find("table", class_="t_view")
        
        if table is None:
            # Method 4: Look for PDF links directly (no table)
            pdf_links = soup.find_all("a", href=lambda x: x and ".pdf" in x.lower())
            if pdf_links:
                self.info(f"Found {len(pdf_links)} PDF links (no table)")
                for link in pdf_links:
                    href = link.get("href")
                    if href:
                        pdf_url = urljoin(self.base_url, href)
                        title = link.get_text(strip=True) or href.split("/")[-1].replace(".pdf", "")
                        
                        # Try to find date nearby
                        date = ""
                        parent = link.find_parent()
                        if parent:
                            date_match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})", parent.get_text())
                            if date_match:
                                date = date_match.group(1)
                        
                        documents.append({
                            "department": "Commissioner and Registrar of Cooperative Societies",
                            "category": section_name,
                            "title": title[:100],
                            "date": date,
                            "language": "Unknown",
                            "size": "",
                            "pdf_url": pdf_url,
                            "local_path": "",
                            "sha256": "",
                            "source_page": section_url,
                        })
                return documents
            
            self.warning("Document table not found.")
            return documents

        rows = table.find_all("tr")

        if len(rows) < 2:
            self.warning("Table has no data rows.")
            return documents

        # Determine column indices from header row
        header_row = rows[0]
        headers = [h.get_text(" ", strip=True).lower() for h in header_row.find_all(["th", "td"])]
        
        # Default column indices
        title_idx = 0
        date_idx = 1
        link_idx = 2
        size_idx = 3
        
        # Map headers to column indices
        for i, h in enumerate(headers):
            h_lower = h.lower()
            # Title/Name columns
            if "नाव" in h_lower or "name" in h_lower or "title" in h_lower or "document" in h_lower:
                title_idx = i
            # Date columns
            elif "दिनांक" in h_lower or "date" in h_lower:
                date_idx = i
            # Download/View columns
            elif "download" in h_lower or "डाउनलोड" in h_lower or "view" in h_lower:
                link_idx = i
            # Size columns
            elif "size" in h_lower or "आकार" in h_lower:
                size_idx = i
            # For GR section: Document Name column
            elif "document name" in h_lower:
                title_idx = i
            # For GR section: DocumentPath column (contains PDF link)
            elif "documentpath" in h_lower:
                link_idx = i

        self.info(f"Headers: {headers}")
        self.info(f"Title col: {title_idx}, Date col: {date_idx}, Link col: {link_idx}, Size col: {size_idx}")

        # Process data rows
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

                # Get size
                size_col = cols[size_idx] if size_idx < len(cols) else None
                size = size_col.get_text(" ", strip=True) if size_col else ""

                # Get PDF URL
                link_col = cols[link_idx] if link_idx < len(cols) else None

                if link_col is None:
                    continue

                # Find link - could be direct or inside a span
                link = link_col.find("a")
                
                if link is None:
                    # Try to find any link in the column
                    links = link_col.find_all("a")
                    for l in links:
                        href = l.get("href")
                        if href and ".pdf" in href.lower():
                            link = l
                            break

                if link is None:
                    continue

                href = link.get("href")

                if not href:
                    continue

                # Build full PDF URL
                pdf_url = urljoin(self.base_url, href)

                # Ensure it's a PDF
                if not pdf_url.lower().endswith(".pdf"):
                    continue

                # Determine language
                language = self.detect_language(title, pdf_url)

                # Clean title (remove extra spaces)
                title = re.sub(r"\s+", " ", title).strip()

                documents.append({
                    "department": "Commissioner and Registrar of Cooperative Societies",
                    "category": section_name,
                    "title": title,
                    "date": date,
                    "language": language,
                    "size": size,
                    "pdf_url": pdf_url,
                    "local_path": "",
                    "sha256": "",
                    "source_page": section_url,  # Now defined!
                })

            except Exception as e:
                self.warning(f"Error parsing row: {e}")

        self.info(f"Extracted {len(documents)} documents")

        return documents

    ##################################################################
    # DETECT LANGUAGE
    ##################################################################

    def detect_language(self, title, pdf_url):

        # Check URL for language indicators
        url_lower = pdf_url.lower()
        if "english" in url_lower or "eng" in url_lower:
            return "English"
        if "marathi" in url_lower or "mar" in url_lower:
            return "Marathi"

        # Check title
        marathi_indicators = [
            "अधिनियम", "नियम", "परिपत्र", "सूचना", "सहकार",
            "संस्था", "उपविधी", "आदर्श", "गृहनिर्माण"
        ]
        
        for indicator in marathi_indicators:
            if indicator in title:
                return "Marathi"

        # Check if title has English characters but no Marathi
        if any(c.isalpha() for c in title) and not any(ord(c) > 127 for c in title):
            return "English"

        return "Unknown"

    ##################################################################
    # BUILD NEXT PAGE URL (for GR section)
    ##################################################################

    def build_next_page_url(self, soup, current_url):

        # Look for pagination links
        pagination = soup.find("table")
        if pagination:
            # Check if it's a pagination table (contains page numbers)
            rows = pagination.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                for col in cols:
                    links = col.find_all("a")
                    for a in links:
                        text = a.get_text(" ", strip=True)
                        if text.isdigit():
                            page_num = int(text)
                            # Try to find current page
                            current_page = 1
                            if "page=" in current_url:
                                match = re.search(r"page=(\d+)", current_url)
                                if match:
                                    current_page = int(match.group(1))
                            
                            if page_num == current_page + 1:
                                href = a.get("href")
                                if href:
                                    return urljoin(self.base_url, href)

        # Try to find "Next" link
        for a in soup.find_all("a"):
            text = a.get_text(" ", strip=True).lower()
            href = a.get("href")
            if href and ("next" in text or "→" in text or "»" in text):
                return urljoin(self.base_url, href)

        return None

    ##################################################################
    # HOUSING SOCIETY RELEVANCE FILTER
    ##################################################################

    def is_relevant(self, document):
        """
        Strict housing society relevance filter.
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
            "Scheme": ["scheme", "योजना"],
            "RTI": ["rti", "माहिती अधिकार"],
            "Publication": ["publication", "प्रकाशन"],
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
            folder = "Sahakarayukta"

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
            "document_id": f"saha_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename[:20]}",
            "title": document.get("title", ""),
            "filename": filename,
            "local_path": str(filepath),
            
            # CRITICAL: Source URLs for chatbot citations
            "pdf_url": document["pdf_url"],
            "source_website": self.source_website,
            "source_page": document.get("source_page", self.base_url),
            
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
        self.info(f"Processing {total} documents (Housing Society Filter)")
        self.info("=" * 70)

        for i, doc in enumerate(self.documents, start=1):

            self.info(f"[{i}/{total}]")

            if not self.is_relevant(doc):
                skipped += 1
                self.info("⏭️  Skipped (Not Housing Society Related)")
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

            csv_file = metadata_dir / "sahakarayukta_metadata.csv"

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
        self.info("Sahakarayukta Started (Housing Society Focus)")
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
            self.info(f"Sections Crawled : {len(self.section_urls)}")
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