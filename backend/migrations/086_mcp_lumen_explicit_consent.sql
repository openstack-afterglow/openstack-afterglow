-- Explicit consent is recorded only by the Lumen approval workflow.
-- Legacy implicit grants deliberately remain NULL and are not dispatchable.
-- Apply before deploying readers/writers that use consented_at.

ALTER TABLE mcp_delegated_grants
    ADD COLUMN IF NOT EXISTS consented_at DATETIME(6) NULL;
