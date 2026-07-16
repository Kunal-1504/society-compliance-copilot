"""
s3_manager.py

Amazon S3 integration for the Maharashtra Government Document Collection
Framework.

This module is intentionally standalone: it has no knowledge of connectors,
scraping, or filtering logic. It is only ever called from main.py, after a
document has already been downloaded, validated, hashed (SHA256) and
recorded in local metadata.

Responsibilities
-----------------
- Mirror the local dataset/ folder structure inside an S3 bucket
- Skip upload if the object already exists in S3 (S3-side duplicate check)
- Retry transient failures (network errors, timeouts) up to N times
- Fail fast (no retry) on credential errors
- Never delete the local file, regardless of upload outcome
- Upload metadata/*.csv to S3 once, after the scraper run finishes

SHA256 is used only for LOCAL duplicate detection (already handled by
MetadataManager). S3-side duplicate detection is based purely on whether
the target key already exists.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, Optional

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    PartialCredentialsError,
    EndpointConnectionError,
)


class S3Manager:
    """
    Thin, dependency-free wrapper around boto3 for uploading scraper
    output to S3. Holds no global state; all configuration is injected
    via the constructor.
    """

    def __init__(
        self,
        config: Dict,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Args:
            config: the global CONFIG dict (reads the "aws" section).
            logger: optional logger instance; a module-level logger is
                created automatically if not provided.
        """

        aws_config = config.get("aws", {})

        self.enabled: bool = aws_config.get("enabled", False)
        self.bucket: str = aws_config.get("s3_bucket_name", "")
        self.prefix: str = aws_config.get("s3_prefix", "dataset").strip("/")
        self.max_retries: int = aws_config.get("max_retries", 3)
        self.retry_backoff_seconds: float = aws_config.get(
            "retry_backoff_seconds", 2.0
        )

        self.dataset_dir: Path = Path(config["storage"]["dataset_directory"])
        self.metadata_dir: Path = Path(config["storage"]["metadata_directory"])

        self.logger = logger or logging.getLogger(__name__)

        # boto3 already multiparts large uploads automatically, but an
        # explicit TransferConfig makes the thresholds visible/tunable
        # instead of relying on hidden library defaults.
        self._transfer_config = TransferConfig(
            multipart_threshold=8 * 1024 * 1024,   # 8 MB
            multipart_chunksize=8 * 1024 * 1024,   # 8 MB
            max_concurrency=10,
            use_threads=True,
        )

        self._client = None

        if not self.enabled:
            self.logger.info("S3Manager disabled (aws.enabled=False in config)")
            return

        if not self.bucket:
            self.logger.warning(
                "S3 enabled but 'aws.s3_bucket_name' is not set — disabling S3Manager"
            )
            self.enabled = False
            return

        self._client = boto3.client(
            "s3",
            region_name=aws_config.get("aws_region"),
            aws_access_key_id=aws_config.get("aws_access_key_id") or None,
            aws_secret_access_key=aws_config.get("aws_secret_access_key") or None,
        )

    # ------------------------------------------------------------------
    # Key building
    # ------------------------------------------------------------------

    def build_s3_key(self, local_path: Path) -> str:
        """
        Build the S3 object key for a local file so the S3 layout exactly
        mirrors the local dataset/ folder structure.

        Example:
            dataset/Government_Resolutions/file.pdf
                -> dataset/Government_Resolutions/file.pdf   (in S3, under prefix)
        """

        local_path = Path(local_path)

        try:
            relative = local_path.relative_to(self.dataset_dir)
        except ValueError:
            relative = Path(local_path.name)

        key = "/".join(relative.parts)

        if self.prefix:
            key = f"{self.prefix}/{key}"

        return key

    # ------------------------------------------------------------------
    # Existence check (S3-side duplicate detection)
    # ------------------------------------------------------------------

    def object_exists(self, key: str) -> bool:
        """
        Check whether an object already exists in S3 via HEAD request.
        Returns False (and logs a warning) if the check itself fails for
        a reason other than "not found" — this never blocks an upload
        attempt on an inconclusive check.
        """

        if not self.enabled or self._client is None:
            return False

        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey", "NotFound"):
                return False
            self.logger.warning(f"Could not verify existence of {key}: {e}")
            return False

    # ------------------------------------------------------------------
    # Upload a single document
    # ------------------------------------------------------------------

    def upload_file(self, local_path: Path) -> Optional[str]:
        """
        Upload a single local file to S3.

        - Skips upload (returns existing URI) if the object already exists.
        - Retries up to `max_retries` times on transient errors.
        - Fails fast (no retry) on credential errors.
        - Never deletes the local file, on success or failure.

        Returns:
            The s3:// URI on success or if already present, else None.
        """

        if not self.enabled or self._client is None:
            return None

        local_path = Path(local_path)

        if not local_path.exists():
            self.logger.error(f"Cannot upload, file not found locally: {local_path}")
            return None

        key = self.build_s3_key(local_path)
        s3_uri = f"s3://{self.bucket}/{key}"

        if self.object_exists(key):
            self.logger.info(f"Already exists in S3: {s3_uri}")
            return s3_uri

        success = self._upload_with_retry(local_path, key)

        return s3_uri if success else None

    # ------------------------------------------------------------------
    # Upload metadata CSVs (run once, after the full scraper run)
    # ------------------------------------------------------------------

    def upload_metadata(self) -> None:
        """
        Upload metadata/master_metadata.csv and all connector-specific
        metadata CSVs to S3. Intended to be called exactly once, after
        the scraper run finishes successfully — metadata files are
        overwritten in S3 (not versioned/skipped), so calling this
        mid-run would upload incomplete data.
        """

        if not self.enabled or self._client is None:
            return

        if not self.metadata_dir.exists():
            self.logger.warning(f"Metadata directory not found: {self.metadata_dir}")
            return

        csv_files = sorted(self.metadata_dir.glob("*.csv"))

        if not csv_files:
            self.logger.warning("No metadata CSV files found to upload")
            return

        for csv_file in csv_files:
            key = f"metadata/{csv_file.name}"
            self._upload_with_retry(csv_file, key)

    # ------------------------------------------------------------------
    # Shared retry logic
    # ------------------------------------------------------------------

    def _upload_with_retry(self, local_path: Path, key: str) -> bool:
        """
        Upload local_path to self.bucket/key, retrying on transient
        errors. Returns True on success, False if all retries exhausted
        or the error is non-retryable (credentials).
        """

        s3_uri = f"s3://{self.bucket}/{key}"

        for attempt in range(1, self.max_retries + 1):

            try:
                self._client.upload_file(
                    str(local_path),
                    self.bucket,
                    key,
                    Config=self._transfer_config,
                )

                self.logger.info(f"Uploaded to S3: {s3_uri}")
                return True

            except (NoCredentialsError, PartialCredentialsError) as e:
                # Retrying will not fix missing/invalid credentials.
                self.logger.error(f"AWS credential error, not retrying: {e}")
                return False

            except (EndpointConnectionError, ClientError) as e:
                self.logger.warning(
                    f"WARNING Retry upload {attempt}/{self.max_retries} "
                    f"for {local_path.name}: {e}"
                )

            except Exception as e:
                self.logger.warning(
                    f"WARNING Retry upload {attempt}/{self.max_retries} "
                    f"(unexpected error) for {local_path.name}: {e}"
                )

            if attempt < self.max_retries:
                time.sleep(self.retry_backoff_seconds * attempt)

        self.logger.error(
            f"ERROR Upload failed after {self.max_retries} attempts, "
            f"local file kept: {local_path}"
        )
        return False
