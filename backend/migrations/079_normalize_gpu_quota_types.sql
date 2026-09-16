-- Normalize gpu_quotas.gpu_type to the canonical alias form used by
-- app.services.gpu_quota.normalize_gpu_alias (uppercase alphanumerics only).
-- Rows that collapse onto the same (project_id, normalized type) keep the most
-- recently updated row (ties: highest id).

DELETE q FROM gpu_quotas q
JOIN gpu_quotas k
  ON k.project_id = q.project_id
 AND UPPER(REGEXP_REPLACE(k.gpu_type, '[^a-zA-Z0-9]', '')) = UPPER(REGEXP_REPLACE(q.gpu_type, '[^a-zA-Z0-9]', ''))
 AND (k.updated_at > q.updated_at OR (k.updated_at = q.updated_at AND k.id > q.id));

UPDATE gpu_quotas
   SET gpu_type = UPPER(REGEXP_REPLACE(gpu_type, '[^a-zA-Z0-9]', '')),
       updated_at = updated_at;
