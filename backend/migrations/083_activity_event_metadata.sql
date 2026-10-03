-- Add optional audit metadata without changing historical activity rows.
ALTER TABLE activity_logs
  ADD COLUMN request_id VARCHAR(64) NULL,
  ADD COLUMN external_id VARCHAR(128) NULL,
  ADD COLUMN event_type VARCHAR(128) NULL,
  ADD COLUMN service VARCHAR(32) NULL,
  ADD COLUMN source VARCHAR(16) NULL,
  ADD COLUMN page VARCHAR(255) NULL,
  ADD COLUMN http_status INT NULL,
  ADD UNIQUE KEY uq_activity_external_id (external_id),
  ADD KEY idx_activity_created_id (created_at, id);
