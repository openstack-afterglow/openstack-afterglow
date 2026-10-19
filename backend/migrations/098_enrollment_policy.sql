-- Apply before policy/approval writers; drain old signup writers at cutover.
-- No policy row is seeded: absence preserves auth.public_signup_enabled and auto
-- admission, with conservative zero core quotas for future personal domains.
-- Neither this queue nor the quota snapshot contains credentials or raw tokens.
CREATE TABLE IF NOT EXISTS enrollment_policy (
    id INT NOT NULL PRIMARY KEY,
    revision INT NOT NULL,
    public_signup_enabled BOOLEAN NOT NULL,
    approval_mode VARCHAR(16) NOT NULL,
    personal_quotas JSON NOT NULL,
    updated_by_user_id VARCHAR(64) NOT NULL,
    updated_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS signup_requests (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    source VARCHAR(16) NOT NULL,
    identity_hash VARCHAR(64) NOT NULL,
    binding_hash VARCHAR(64) NOT NULL,
    email VARCHAR(255) NOT NULL,
    domain_id VARCHAR(64) NULL,
    provider_id VARCHAR(64) NULL,
    status VARCHAR(16) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    reviewed_at DATETIME(6) NULL,
    reviewed_by_user_id VARCHAR(64) NULL,
    consumed_at DATETIME(6) NULL,
    consumed_by_user_id VARCHAR(64) NULL,
    UNIQUE KEY uq_signup_request_identity (identity_hash),
    INDEX idx_signup_request_status_id (status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE domain_enrollments ADD COLUMN IF NOT EXISTS personal_quotas JSON NULL;
