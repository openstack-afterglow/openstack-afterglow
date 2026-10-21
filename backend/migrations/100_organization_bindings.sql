-- Apply after 099 before enabling configured OIDC organization writers.
-- No native tenant adoption/backfill: existing identities and memberships remain.
-- creating/uncertain fence unknown creation outcomes; settle exact intent
-- with native evidence, never delete/retry by display name or guessed IDs.
CREATE TABLE IF NOT EXISTS organization_bindings (
    binding_key VARCHAR(64) NOT NULL PRIMARY KEY,
    issuer_url VARCHAR(2048) NOT NULL,
    external_org_id VARCHAR(255) NOT NULL,
    client_id VARCHAR(255) NOT NULL,
    domain_id VARCHAR(64) NULL UNIQUE,
    creator_user_id VARCHAR(64) NOT NULL,
    intent_id VARCHAR(36) NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
