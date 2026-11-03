-- Schema-before-writer: apply before deploying any ongoing OAuth issuer,
-- reader, or cleanup worker. Roll back code only after revoking ongoing grants;
-- old readers cannot safely interpret unbounded OAuth authority.
-- Existing rows retain finite consent; no credential or deadline is extended.

ALTER TABLE mcp_delegated_grants
    ADD COLUMN IF NOT EXISTS oauth_ongoing BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS issued_role_ceiling JSON NULL;

ALTER TABLE mcp_delegated_grants
    DROP CONSTRAINT IF EXISTS chk_mcp_grant_expiry;

ALTER TABLE mcp_delegated_grants
    ADD CONSTRAINT chk_mcp_grant_expiry
    CHECK (expires_at IS NOT NULL OR source = 'personal_token' OR (source = 'oauth' AND oauth_ongoing = TRUE));

ALTER TABLE mcp_delegated_grants
    DROP CONSTRAINT IF EXISTS chk_mcp_grant_ongoing;

ALTER TABLE mcp_delegated_grants
    ADD CONSTRAINT chk_mcp_grant_ongoing
    CHECK (oauth_ongoing = FALSE OR (source = 'oauth' AND expires_at IS NULL
        AND COALESCE(LOWER(JSON_TYPE(issued_role_ceiling)) = 'object', 0)));

ALTER TABLE mcp_oauth_tokens
    MODIFY COLUMN expires_at DATETIME(6) NULL;

ALTER TABLE mcp_oauth_tokens
    DROP CONSTRAINT IF EXISTS chk_mcp_oauth_token_expiry;

ALTER TABLE mcp_oauth_tokens
    ADD CONSTRAINT chk_mcp_oauth_token_expiry
    CHECK (expires_at IS NOT NULL OR token_type = 'refresh');
