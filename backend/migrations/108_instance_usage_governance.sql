-- Additive only. Apply before any usage-governance writers and coordinate all API cohorts.
-- Old binaries bypass review policy: mixed-version writers are not a safe rollout state.
CREATE TABLE IF NOT EXISTS instance_usage_policies (
    cloud_id CHAR(64) NOT NULL,
    domain_id VARCHAR(64) NOT NULL,
    review_required BOOLEAN NOT NULL,
    revision CHAR(32) NOT NULL,
    updated_by VARCHAR(64) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (cloud_id, domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS instance_usage_extension_requests (
    id CHAR(32) NOT NULL PRIMARY KEY,
    cloud_id CHAR(64) NOT NULL,
    domain_id VARCHAR(64) NOT NULL,
    project_id VARCHAR(64) NOT NULL,
    instance_id VARCHAR(64) NOT NULL,
    instance_name VARCHAR(255) DEFAULT NULL,
    requested_by VARCHAR(64) NOT NULL,
    requested_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    reason VARCHAR(255) NOT NULL,
    schedule_revision CHAR(32) NOT NULL,
    policy_revision CHAR(32) NOT NULL,
    revision CHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL,
    reviewed_by VARCHAR(64) DEFAULT NULL,
    reviewed_at DATETIME DEFAULT NULL,
    applied_schedule JSON DEFAULT NULL,
    KEY idx_instance_usage_request_scope (cloud_id, domain_id, project_id, requested_at),
    KEY idx_instance_usage_request_target (cloud_id, project_id, instance_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
