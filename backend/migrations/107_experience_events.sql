-- Opt-in semantic diagnostics. No existing business table or retention job is changed.
CREATE TABLE IF NOT EXISTS experience_catalogs (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    revision VARCHAR(80) NOT NULL,
    `key` VARCHAR(180) NOT NULL,
    locale VARCHAR(16) NOT NULL,
    template TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS experience_events (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    received_at DATETIME(6) NOT NULL,
    owner_key VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    project_id VARCHAR(64) NOT NULL,
    segment_id VARCHAR(36) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    action_id VARCHAR(36) NULL,
    source VARCHAR(16) NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    catalog_id VARCHAR(64) NULL,
    data JSON NOT NULL,
    CONSTRAINT fk_experience_event_catalog FOREIGN KEY (catalog_id) REFERENCES experience_catalogs(id) ON DELETE RESTRICT,
    UNIQUE KEY uq_experience_owner_event (owner_key, segment_id, event_id),
    KEY ix_experience_scope_segment (project_id, segment_id, id),
    KEY ix_experience_segment_action (segment_id, action_id, id),
    KEY ix_experience_retention (received_at, id),
    KEY ix_experience_catalog (catalog_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS experience_operation_links (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    kind VARCHAR(32) NOT NULL,
    operation_id VARCHAR(128) NOT NULL,
    owner_key VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    project_id VARCHAR(64) NOT NULL,
    segment_id VARCHAR(36) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    context JSON NOT NULL,
    KEY ix_experience_link_retention (created_at),
    KEY ix_experience_link_segment (segment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS experience_holds (
    owner_key VARCHAR(64) NOT NULL,
    segment_id VARCHAR(36) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (owner_key, segment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS experience_aggregates (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    day DATE NOT NULL,
    project_id VARCHAR(64) NOT NULL,
    source VARCHAR(16) NOT NULL,
    feature VARCHAR(32) NOT NULL,
    event_type VARCHAR(48) NOT NULL,
    count BIGINT NOT NULL,
    KEY ix_experience_aggregate_retention (day)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS experience_maintenance (
    id INTEGER NOT NULL PRIMARY KEY,
    revision BIGINT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
