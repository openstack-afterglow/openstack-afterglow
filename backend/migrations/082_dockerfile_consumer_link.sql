-- Retain the validated consumer request and resulting VM across asynchronous imports.
ALTER TABLE layer_import_jobs
  ADD COLUMN consumer_spec JSON NULL,
  ADD COLUMN consume_id INT NULL,
  ADD CONSTRAINT fk_layer_import_consume FOREIGN KEY (consume_id)
    REFERENCES layer_consumes(id) ON DELETE SET NULL;
