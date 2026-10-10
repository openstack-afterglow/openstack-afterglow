-- Immutable approved-project snapshots and restricted per-project credentials.
-- Existing grants keep NULL metadata: runtime interprets that as the exact
-- original owner_project_id singleton, never as current Keystone inventory.
-- MariaDB 10.11+; safe to reapply without expanding or rewriting old authority.

ALTER TABLE mcp_delegated_grants
    ADD COLUMN IF NOT EXISTS project_scope VARCHAR(20) NOT NULL DEFAULT 'current' AFTER access_level,
    ADD COLUMN IF NOT EXISTS approved_projects JSON NULL AFTER project_scope;

ALTER TABLE mcp_delegated_grants
    DROP CONSTRAINT IF EXISTS chk_mcp_grant_source,
    DROP CONSTRAINT IF EXISTS chk_mcp_grant_project_scope;

ALTER TABLE mcp_delegated_grants
    ADD CONSTRAINT chk_mcp_grant_source CHECK (source IN ('personal_token', 'oauth', 'lumen')),
    ADD CONSTRAINT chk_mcp_grant_project_scope CHECK (project_scope IN ('current', 'selected', 'all'));

CREATE TABLE IF NOT EXISTS mcp_project_credentials (
    grant_id CHAR(36) NOT NULL,
    project_id VARCHAR(64) NOT NULL,
    upstream_credential_name VARCHAR(128) NOT NULL,
    application_credential_id VARCHAR(128) NULL,
    credential_ciphertext MEDIUMTEXT NULL,
    cleanup_pending BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (grant_id, project_id),
    UNIQUE KEY uq_mcp_project_credentials_upstream_name (upstream_credential_name),
    CONSTRAINT fk_mcp_project_credentials_grant
        FOREIGN KEY (grant_id) REFERENCES mcp_delegated_grants(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
