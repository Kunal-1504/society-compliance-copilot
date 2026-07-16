"""
Source Manager

Responsible for:

- Loading connectors
- Running connectors
- Merging discovered documents
- Removing duplicates
"""

from typing import Dict, List

from sources.gr_portal_connector import GRPortalConnector


class SourceManager:

    def __init__(self, config, logger):

        self.config = config
        self.logger = logger

        self.connectors = []

        self._register_connectors()

    def _register_connectors(self):

        self.logger.info("Registering connectors...")

        self.connectors.append(
            GRPortalConnector(
                self.config,
                self.logger
            )
        )

        self.logger.info(
            f"{len(self.connectors)} connector(s) registered."
        )

    def discover_documents(self):

        all_documents = []

        for connector in self.connectors:

            try:

                self.logger.info(
                    f"Running {connector.name}"
                )

                docs = connector.scrape()

                connector.download_all()

                self.logger.info(
                    f"{len(docs)} document(s) discovered."
                )

                all_documents.extend(docs)

            except Exception as e:

                self.logger.exception(
                    f"{connector.name} failed : {e}"
                )

        return self.remove_duplicates(all_documents)

    def remove_duplicates(self, documents):

        unique = {}

        for doc in documents:

            url = doc.get("pdf_url")

            if not url:
                continue

            unique[url] = doc

        return list(unique.values())
