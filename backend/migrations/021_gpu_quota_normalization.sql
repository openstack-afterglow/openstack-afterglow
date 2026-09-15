-- Normalize legacy GPU quota rows before enforcing the ORM contract.
-- Invalid ownership/alias rows are discarded (absent quota fails closed), invalid limits become zero,
-- and duplicate normalized aliases converge to the strictest finite limit on the oldest row.

SET @gpu_quota_unique_exists := (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'gpu_quotas'
      AND index_name = 'uq_gpu_quotas_project_gpu_type'
);
SET @gpu_quota_drop_unique_sql := IF(
    @gpu_quota_unique_exists > 0,
    'ALTER TABLE gpu_quotas DROP INDEX uq_gpu_quotas_project_gpu_type',
    'SELECT 1'
);
PREPARE gpu_quota_drop_unique_stmt FROM @gpu_quota_drop_unique_sql;
EXECUTE gpu_quota_drop_unique_stmt;
DEALLOCATE PREPARE gpu_quota_drop_unique_stmt;

DELETE FROM gpu_quotas
WHERE project_id IS NULL
   OR TRIM(project_id) = ''
   OR gpu_type IS NULL
   OR REGEXP_REPLACE(UPPER(TRIM(gpu_type)), '[^A-Z0-9]', '') = ''
   OR REGEXP_REPLACE(UPPER(TRIM(gpu_type)), '[^A-Z0-9]', '') LIKE '%AUDIO%';

UPDATE gpu_quotas
SET project_id = TRIM(project_id),
    gpu_type = REGEXP_REPLACE(UPPER(TRIM(gpu_type)), '[^A-Z0-9]', ''),
    `limit` = CASE WHEN `limit` IS NULL OR `limit` < -1 THEN 0 ELSE `limit` END,
    created_at = COALESCE(created_at, CURRENT_TIMESTAMP(6)),
    updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP(6));

DROP TEMPORARY TABLE IF EXISTS gpu_quota_normalized_rows;
CREATE TEMPORARY TABLE gpu_quota_normalized_rows AS
SELECT MIN(id) AS keep_id,
       project_id,
       gpu_type,
       CASE
           WHEN SUM(CASE WHEN `limit` = -1 THEN 1 ELSE 0 END) = COUNT(*) THEN -1
           ELSE MIN(CASE WHEN `limit` = -1 THEN 2147483647 ELSE `limit` END)
       END AS normalized_limit,
       MIN(created_at) AS created_at,
       MAX(updated_at) AS updated_at
FROM gpu_quotas
GROUP BY project_id, gpu_type;

UPDATE gpu_quotas AS quota
JOIN gpu_quota_normalized_rows AS normalized ON normalized.keep_id = quota.id
SET quota.`limit` = normalized.normalized_limit,
    quota.created_at = normalized.created_at,
    quota.updated_at = normalized.updated_at;

DELETE quota
FROM gpu_quotas AS quota
LEFT JOIN gpu_quota_normalized_rows AS normalized ON normalized.keep_id = quota.id
WHERE normalized.keep_id IS NULL;

DROP TEMPORARY TABLE gpu_quota_normalized_rows;

ALTER TABLE gpu_quotas
    MODIFY project_id VARCHAR(64) NOT NULL,
    MODIFY gpu_type VARCHAR(64) NOT NULL,
    MODIFY `limit` INT NOT NULL,
    MODIFY created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    MODIFY updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6);

ALTER TABLE gpu_quotas
    ADD UNIQUE KEY uq_gpu_quotas_project_gpu_type (project_id, gpu_type);
