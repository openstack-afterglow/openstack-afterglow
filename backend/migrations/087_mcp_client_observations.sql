-- Self-reported initialization evidence only; legacy grants retain unknown identity.
-- Apply before deploying observation readers/writers. No authority is backfilled.
ALTER TABLE mcp_delegated_grants
    ADD COLUMN IF NOT EXISTS client_observations JSON NULL;
