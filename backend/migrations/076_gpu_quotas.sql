-- GPU Quotas Authority table for Afterglow local persistence.
-- Restores local gpu_quotas schema after cutover from Drover.

CREATE TABLE IF NOT EXISTS gpu_quotas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL,
    gpu_type VARCHAR(64) NOT NULL,
    `limit` INT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_gpu_quotas_project_gpu_type (project_id, gpu_type),
    KEY idx_gpu_quotas_project_id (project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
