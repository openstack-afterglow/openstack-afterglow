-- Explicitly unbounded personal keys keep the same owner/project, epoch and
-- revocation lifecycle. OAuth and internal Lumen grants remain bounded.
-- Apply before enabling a new writer; old readers cannot handle NULL deadlines.

ALTER TABLE mcp_delegated_grants
    MODIFY COLUMN expires_at DATETIME(6) NULL;

ALTER TABLE mcp_delegated_grants
    DROP CONSTRAINT IF EXISTS chk_mcp_grant_expiry;

ALTER TABLE mcp_delegated_grants
    ADD CONSTRAINT chk_mcp_grant_expiry
    CHECK (expires_at IS NOT NULL OR source = 'personal_token');
