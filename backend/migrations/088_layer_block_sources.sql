-- Durable immutable source identity and recoverable preallocated Glance upload UUID.
ALTER TABLE layer_artifacts
    ADD COLUMN IF NOT EXISTS block_source JSON NULL AFTER source_metadata;
