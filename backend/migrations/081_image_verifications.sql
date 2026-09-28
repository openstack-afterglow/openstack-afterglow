-- Administrator approvals are Afterglow-owned; no Glance property or tag grants trust.
-- Apply in manifest logical-ID order on databases where auto-create is off;
-- app.bootstrap/create_all also creates this table on freshly bootstrapped DBs.
CREATE TABLE IF NOT EXISTS image_verifications (
    image_id VARCHAR(64) NOT NULL PRIMARY KEY,
    owner_id VARCHAR(64) NOT NULL,
    image_created_at DATETIME(6) NOT NULL,
    hash_algorithm VARCHAR(16) NOT NULL,
    hash_value VARCHAR(128) NOT NULL,
    verified_by VARCHAR(64) NOT NULL,
    verified_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
