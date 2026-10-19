-- Schema-before-writer cutover: drain old enrollment API writers before enabling
-- public signup. NULL is a global registration's unassigned personal home, never
-- an invitation target. The accepting writer journals the exact new home ID.
-- This is an additive nullable expansion; legacy invitation writers still work,
-- but old registration writers/readers MUST NOT run alongside the new endpoint.
ALTER TABLE domain_enrollments MODIFY COLUMN domain_id VARCHAR(64) NULL;

-- Retire outstanding arbitrary-domain public admission links. Do not touch
-- accepted accounts, invitations, or interrupted native-write recovery journals;
-- no native users, passwords, domains or grants are moved/reset by this migration.
UPDATE domain_enrollments
SET status = 'revoked'
WHERE kind = 'registration'
  AND domain_id IS NOT NULL
  AND status IN ('pending', 'delivery_pending');

-- Rollback requires draining the new writer and resolving/deleting only pending
-- NULL-domain registration rows before restoring NOT NULL. Image-only rollback
-- cannot restore old public admission links or safely reinterpret global links.
