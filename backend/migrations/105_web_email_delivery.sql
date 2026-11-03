-- Schema-before-writer. Additive outgoing intent/preferences only; no native writes.
-- Bodies and subjects live only in purpose-bound v3 encrypted per-recipient payloads.
CREATE TABLE IF NOT EXISTS email_operations (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    actor_id VARCHAR(64) NOT NULL,
    operation_id VARCHAR(36) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    kind VARCHAR(24) NOT NULL,
    announcement_id BIGINT NULL,
    audience_pending BOOLEAN NOT NULL DEFAULT FALSE,
    announcement_fingerprint VARCHAR(64) NULL,
    notification_activity_id BIGINT NULL,
    created_at DATETIME(6) NOT NULL,
    UNIQUE KEY uq_email_actor_operation (actor_id, operation_id),
    UNIQUE KEY uq_email_notification_activity (notification_activity_id),
    KEY idx_email_operation_audience (kind, audience_pending, created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS email_deliveries (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    operation_key VARCHAR(32) NOT NULL,
    operation_id VARCHAR(36) NOT NULL,
    kind VARCHAR(24) NOT NULL,
    user_id VARCHAR(64) NULL,
    identity_domain_id VARCHAR(64) NULL,
    project_id VARCHAR(64) NULL,
    recipient_email VARCHAR(255) NOT NULL,
    payload_encrypted TEXT NOT NULL,
    message_id VARCHAR(255) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    error_code VARCHAR(64) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    available_at DATETIME(6) NOT NULL,
    UNIQUE KEY uq_email_message_id (message_id),
    KEY idx_email_delivery_pending (status, available_at, id),
    KEY idx_email_delivery_operation (operation_key),
    KEY idx_email_delivery_created (created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS email_preferences (
    user_id VARCHAR(64) NOT NULL,
    identity_domain_id VARCHAR(64) NOT NULL,
    announcements BOOLEAN NOT NULL DEFAULT TRUE,
    resource_alerts BOOLEAN NOT NULL DEFAULT FALSE,
    resource_alerts_enabled_at DATETIME(6) NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (user_id, identity_domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS email_notification_cursors (
    name VARCHAR(32) NOT NULL PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    enabled_at DATETIME(6) NOT NULL,
    scan_after_id BIGINT NOT NULL DEFAULT 0,
    scan_until_id BIGINT NOT NULL DEFAULT 0,
    updated_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
