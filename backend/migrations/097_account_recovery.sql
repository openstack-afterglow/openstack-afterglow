-- Additive schema: apply before mounting recovery/email-change writers.
-- Existing writers do not use this table. Drain unverified profile email writers
-- at cutover; rolling back to those writers reopens the ownership bypass.
-- Retain dispatching/outcome_unknown records: never replay a native mutation
-- from a token journal, even after restart or image rollback.
CREATE TABLE IF NOT EXISTS account_recoveries (
    token_hash VARCHAR(64) NOT NULL PRIMARY KEY,
    kind VARCHAR(16) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    identity_domain_id VARCHAR(64) NOT NULL,
    original_email VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    status VARCHAR(24) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    consumed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_account_recovery_user (user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
