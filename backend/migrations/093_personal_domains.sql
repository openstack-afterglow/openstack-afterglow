-- Additive durable provenance for NEW human personal identity domains only.
-- Existing users/domains/enrollments are not moved or renamed.
-- Keep added_grants nullable so an old writer can still insert during rollout.
-- New writers always journal an array; NULL means no new multi-project journal.
ALTER TABLE domain_enrollments
    ADD COLUMN personal_domain_name VARCHAR(64) NULL,
    ADD COLUMN identity_domain_id VARCHAR(64) NULL,
    ADD COLUMN identity_native_name VARCHAR(64) NULL,
    ADD COLUMN domain_creation_uncertain BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN personal_project_id VARCHAR(64) NULL,
    ADD COLUMN project_creation_uncertain BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN added_grants JSON NULL;
UPDATE domain_enrollments SET added_grants = JSON_ARRAY() WHERE added_grants IS NULL;
