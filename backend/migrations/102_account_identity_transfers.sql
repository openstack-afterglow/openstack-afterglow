-- Durable, encrypted association-transfer snapshots. No native user/resource migration.
CREATE TABLE IF NOT EXISTS account_identity_transfers (
    binding_key VARCHAR(64) NOT NULL PRIMARY KEY,
    status VARCHAR(24) NOT NULL,
    source_user_id VARCHAR(64) NOT NULL,
    target_user_id VARCHAR(64) NULL,
    snapshot_ciphertext TEXT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
