-- Preserve legacy NFS consumers and add durable block-consumer lifecycle state.
ALTER TABLE layer_consumes
  ADD COLUMN transport VARCHAR(16) NOT NULL DEFAULT 'nfs',
  ADD COLUMN run_id CHAR(32) NULL,
  ADD COLUMN resources JSON NULL,
  ADD COLUMN cleanup_state VARCHAR(32) NULL;
