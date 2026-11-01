-- Apply before deploying any backend containing this AccountRecovery model:
-- every recovery kind selects the mapped column, not only password creation.
-- Bootstrap create_tables() does not add columns to existing tables.
-- Legacy proofs deliberately retain NULL: they cannot authorize initial
-- password creation without an exact native permanent identity revision bound
-- in the same issuance transaction.
ALTER TABLE account_recoveries
    ADD COLUMN IF NOT EXISTS native_identity_revision VARCHAR(128) NULL;
