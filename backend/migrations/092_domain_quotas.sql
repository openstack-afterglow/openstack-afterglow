-- Additive policy and native-intent journal. Existing quotas/grants are not rewritten.
-- Apply before enabling new writers. Old writers ignore budgets: mixed-version
-- native quota writers MUST be drained before configuring ceilings. Downgrading
-- application code does not preserve enforcement; retain these tables/journals.
CREATE TABLE IF NOT EXISTS domain_quota_policies (
    domain_id VARCHAR(64) NOT NULL PRIMARY KEY,
    revision INT NOT NULL DEFAULT 0,
    ceilings JSON NOT NULL,
    defaults JSON NOT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS domain_quota_operations (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    domain_id VARCHAR(64) NOT NULL,
    project_id VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    requested JSON NOT NULL,
    sections JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_domain_quota_operation_scope (domain_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
