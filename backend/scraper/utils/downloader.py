"""
Downloader

Responsible for:
- Downloading PDFs
- Creating category folders
- Verifying PDF files
- Updating metadata
- Avoiding duplicate downloads
"""

import requests
from pathlib import Path
from urllib.parse import urlparse
import time



class Downloader:

    def __init__(
        self,
        config,
        metadata_manager,
        logger
    ):

        self.config = config
        self.logger = logger
        self.metadata = metadata_manager

        self.dataset_dir = Path(
            config["storage"]["dataset_directory"]
        )

        self.dataset_dir.mkdir(
            exist_ok=True
        )

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })


    def download_documents(self, documents):

        downloaded = 0
        failed = 0

        for document in documents:

            try:

                if self.download(document):
                    downloaded += 1
                else:
                    failed += 1

            except Exception as e:

                failed += 1

                self.logger.exception(
                    f"Download failed : {e}"
                )

        self.logger.info(
            f"Downloaded={downloaded} Failed={failed}"
        )

    def download(self, document):

        pdf_url = document["pdf_url"]

        if self.metadata.exists(pdf_url):

            self.logger.info(
                f"Already exists : {pdf_url}"
            )

            return True

        category = document.get(
            "category",
            "Others"
        )

        folder = self.dataset_dir / category

        folder.mkdir(
            parents=True,
            exist_ok=True
        )

        filename = self.generate_filename(document)

        filepath = folder / filename

        self.logger.info(
            f"Downloading {filename}"
        )

        response = self.session.get(
            pdf_url,
            timeout=60,
            stream=True,
            allow_redirects=True
        )

        if response.status_code != 200:

            self.logger.warning(
                f"HTTP {response.status_code}"
            )

            return False

        with open(filepath, "wb") as f:

            for chunk in response.iter_content(8192):

                if chunk:
                    f.write(chunk)

        if not self.is_pdf(filepath):

            filepath.unlink(
                missing_ok=True
            )

            self.logger.warning(
                "Downloaded file is not PDF"
            )

            return False

        document["status"] = "Downloaded"

        self.metadata.add(document)

        self.metadata.update_download(
            pdf_url,
            filepath
        )

        self.logger.info(
            f"Saved {filepath}"
        )

        time.sleep(1)

        return True

    def generate_filename(self, document):

        code = document.get(
            "unique_code",
            "document"
        )

        title = document.get(
            "title",
            "document"
        )

        title = (
            title
            .replace("/", "_")
            .replace("\\", "_")
            .replace(":", "")
            .replace("*", "")
            .replace("?", "")
            .replace('"', "")
            .replace("<", "")
            .replace(">", "")
            .replace("|", "")
        )

        title = title[:80]

        return f"{code}_{title}.pdf"

    def is_pdf(self, filepath):

        try:

            with open(filepath, "rb") as f:

                header = f.read(4)

            return header == b"%PDF"

        except:

            return False
