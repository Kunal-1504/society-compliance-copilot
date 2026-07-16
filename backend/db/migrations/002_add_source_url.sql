-- backend/db/migrations/002_add_source_url.sql
-- Adds an optional official-website URL per document. NULL is expected
-- and normal until URLs are backfilled — retrieval should COALESCE to
-- the existing S3 URL when this is empty (see query note below).

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS source_url TEXT,
    ADD COLUMN IF NOT EXISTS source_url_verified BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS source_url_found_via TEXT;  -- 'metadata' | 'manual' | 'web_search' | 'scraper'

COMMENT ON COLUMN documents.source_url IS
    'Official government website URL for this document, if known. NULL until backfilled — display layer should fall back to the S3 URL when NULL.';
COMMENT ON COLUMN documents.source_url_verified IS
    'True once a human has confirmed this URL actually points at this exact document (not just a plausible guess).';

-- Example of the fallback pattern your retrieval query should use:
--   SELECT COALESCE(source_url, s3_url) AS display_url, source_url_verified
--   FROM documents WHERE id = ...
-- This means nothing in the chat UI needs to change based on whether a
-- given document has been backfilled yet — the query always returns
-- *a* usable link, official when available, S3 otherwise.