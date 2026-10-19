-- Per-domain login policy and federated identity-provider configuration.
-- Additive only: absent policy rows keep the documented default (password enabled,
-- signup disabled, unrestricted login email allowlist). No existing user, project
-- or role is migrated. Provider client secrets are domain/provider-bound AEAD ciphertext.

CREATE TABLE IF NOT EXISTS domain_login_policies (
    domain_id VARCHAR(64) NOT NULL,
    password_enabled TINYINT(1) NOT NULL DEFAULT 1,
    allowed_email_domains JSON NOT NULL,
    signup_enabled TINYINT(1) NOT NULL DEFAULT 0,
    signup_email_domains JSON NOT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    updated_by_user_id VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- A provider is offered for testing while unverified. Only a successful native
-- session issuance stamps verified_revision for the exact configuration revision;
-- never backfill proof from enabled/configured rows. Security edits clear proof.
CREATE TABLE IF NOT EXISTS domain_identity_providers (
    id CHAR(36) NOT NULL,
    domain_id VARCHAR(64) NOT NULL,
    name VARCHAR(64) NOT NULL,
    kind VARCHAR(16) NOT NULL,
    issuer_url VARCHAR(512) NULL,
    authorization_url VARCHAR(512) NULL,
    token_url VARCHAR(512) NULL,
    api_url VARCHAR(512) NULL,
    client_id VARCHAR(255) NOT NULL,
    client_secret_ciphertext TEXT NOT NULL,
    scopes JSON NOT NULL,
    keystone_idp_id VARCHAR(64) NOT NULL,
    keystone_protocol_id VARCHAR(64) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    revision BIGINT NOT NULL DEFAULT 1,
    verified_revision BIGINT NULL,
    verified_at DATETIME(6) NULL,
    federation_token_type VARCHAR(16) NOT NULL DEFAULT 'id_token',
    token_endpoint_auth_method VARCHAR(32) NULL,
    created_by_user_id VARCHAR(64) NOT NULL,
    updated_by_user_id VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_domain_identity_provider_name (domain_id, name),
    KEY idx_domain_identity_provider_domain (domain_id, enabled),
    CONSTRAINT chk_domain_identity_provider_kind CHECK (kind IN ('oidc', 'github'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
