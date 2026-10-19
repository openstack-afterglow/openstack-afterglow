-- Additive native ownership mutation fence; apply before enabling new writers.
-- Drain old ownership writers before this cutover. A timeout/readback does not
-- establish native settlement. Retain unresolved journals across upgrades and
-- rollback; old writers cannot enforce this fence and must remain disabled.
CREATE TABLE IF NOT EXISTS project_ownership_transfers (
    project_id VARCHAR(64) NOT NULL PRIMARY KEY,
    id VARCHAR(36) NOT NULL UNIQUE,
    domain_id VARCHAR(64) NOT NULL,
    from_user_id VARCHAR(64) NOT NULL,
    to_user_id VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    stage VARCHAR(24) NOT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
