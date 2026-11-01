-- Schema-before-writer: durable manual review only; never a quota authority.
-- Additive table: older backends ignore it; newer backends fail closed without it.
CREATE TABLE IF NOT EXISTS gpu_quota_requests (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    domain_id VARCHAR(64) NOT NULL,
    project_id VARCHAR(64) NOT NULL,
    requester_id VARCHAR(64) NOT NULL,
    gpu_profile_name VARCHAR(64) NOT NULL,
    resource_class VARCHAR(64) NOT NULL,
    gpu_profile_fingerprint VARCHAR(64) NOT NULL,
    additional INT NOT NULL,
    baseline_limit INT NOT NULL,
    target_limit INT NOT NULL,
    pool_revision INT NOT NULL,
    reason VARCHAR(2000) NOT NULL DEFAULT '',
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    created_at DATETIME(6) NOT NULL,
    reviewer_id VARCHAR(64) NULL,
    reviewed_at DATETIME(6) NULL,
    note VARCHAR(2000) NOT NULL DEFAULT '',
    KEY idx_gpu_request_domain_status (domain_id, status, created_at, id),
    KEY idx_gpu_request_domain_created (domain_id, created_at, id),
    KEY idx_gpu_request_status (status, created_at, id),
    KEY idx_gpu_request_created (created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
