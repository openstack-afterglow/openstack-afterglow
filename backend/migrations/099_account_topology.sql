-- Drain old human enrollment writers before enabling the shared topology writer.
-- No native identities, grants, credentials or historical journals are migrated.
-- Older writers must not run concurrently after cutover; rollback is source-only
-- with human creation disabled, not a destructive DROP of these intent records.
ALTER TABLE domain_enrollments ADD COLUMN IF NOT EXISTS personal_domain_id VARCHAR(64) NULL;
ALTER TABLE domain_enrollments ADD COLUMN IF NOT EXISTS personal_project_name VARCHAR(255) NULL;

CREATE TABLE IF NOT EXISTS shared_domain_intents (
    kind VARCHAR(16) NOT NULL PRIMARY KEY,
    marker VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    domain_id VARCHAR(64) NULL,
    history JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_shared_domain_marker (marker)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS personal_project_intents (
    token_hash VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    primary_user_id VARCHAR(64) NULL,
    `primary` BOOLEAN NOT NULL DEFAULT TRUE,
    identity_domain_id VARCHAR(64) NOT NULL,
    description VARCHAR(255) NOT NULL DEFAULT '',
    status VARCHAR(24) NOT NULL,
    personal_domain_id VARCHAR(64) NOT NULL,
    personal_project_name VARCHAR(255) NOT NULL,
    personal_project_id VARCHAR(64) NULL,
    project_creation_uncertain BOOLEAN NOT NULL DEFAULT FALSE,
    added_grants JSON NOT NULL,
    personal_quotas JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_personal_primary_user (primary_user_id),
    INDEX ix_personal_project_intents_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
