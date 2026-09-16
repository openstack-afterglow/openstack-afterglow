-- Short-lived GPU quota claims for Afterglow-controlled admissions.
-- These reservations do not govern direct Nova API creates.

CREATE TABLE IF NOT EXISTS gpu_quota_reservations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    reservation_id CHAR(36) NOT NULL,
    project_id VARCHAR(64) NOT NULL,
    gpu_type VARCHAR(64) NOT NULL,
    amount INT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    server_id VARCHAR(64) DEFAULT NULL,
    expires_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_gpu_quota_reservation_type (reservation_id, gpu_type),
    KEY idx_gpu_quota_reservations_project_active (project_id, gpu_type, status, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
