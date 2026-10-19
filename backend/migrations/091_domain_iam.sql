-- Additive only. No legacy identity, grants, invitations or domain records are moved.
-- New writers require this table before rollout; old writers ignore it. No DROP rollback.
CREATE TABLE IF NOT EXISTS domain_enrollments (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    kind VARCHAR(16) NOT NULL,
    domain_id VARCHAR(64) NOT NULL,
    email VARCHAR(255) NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    project_id VARCHAR(64) NULL,
    role_ids JSON NOT NULL,
    invited_by VARCHAR(64) NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    user_id VARCHAR(64) NULL,
    project_name VARCHAR(255) NOT NULL DEFAULT '',
    account_name VARCHAR(255) NULL,
    new_user BOOLEAN NOT NULL DEFAULT FALSE,
    requested_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    creation_uncertain BOOLEAN NOT NULL DEFAULT FALSE,
    added_role_ids JSON NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    accepted_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_domain_enrollment_token (token_hash),
    KEY idx_domain_enrollment_scope (domain_id, kind, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
