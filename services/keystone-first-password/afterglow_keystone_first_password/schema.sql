-- Apply only with EVERY Keystone/password writer stopped, after db_sync.
-- TOI must be active. Validate each cluster member before resuming writers.
-- No IF NOT EXISTS: partial installation requires offline operator recovery.
CREATE TABLE afterglow_password_guard (
    user_id VARCHAR(64) NOT NULL,
    revision BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id)
) ENGINE=InnoDB;
-- No FK: certification keys survive native user DELETE/recreation.
INSERT INTO afterglow_password_guard(user_id) SELECT id FROM `user`;
-- afterglow-statement
CREATE TRIGGER afterglow_password_insert BEFORE INSERT ON password FOR EACH ROW
BEGIN
    DECLARE subject VARCHAR(64);
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    SELECT user_id INTO subject FROM local_user WHERE id = NEW.local_user_id;
    UPDATE afterglow_password_guard SET revision = revision + 1 WHERE user_id = subject;
    IF ROW_COUNT() <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Initial password guard missing'; END IF;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_password_update BEFORE UPDATE ON password FOR EACH ROW
BEGIN
    DECLARE subject VARCHAR(64);
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    IF NOT (OLD.local_user_id <=> NEW.local_user_id) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Password owner change forbidden'; END IF;
    SELECT user_id INTO subject FROM local_user WHERE id = OLD.local_user_id;
    UPDATE afterglow_password_guard SET revision = revision + 1 WHERE user_id = subject;
    IF ROW_COUNT() <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Initial password guard missing'; END IF;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_password_delete BEFORE DELETE ON password FOR EACH ROW
BEGIN
    DECLARE subject VARCHAR(64);
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    SELECT user_id INTO subject FROM local_user WHERE id = OLD.local_user_id;
    UPDATE afterglow_password_guard SET revision = revision + 1 WHERE user_id = subject;
    IF ROW_COUNT() <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Initial password guard missing'; END IF;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_local_insert BEFORE INSERT ON local_user FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard SET revision = revision + 1 WHERE user_id = NEW.user_id;
    IF ROW_COUNT() <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Initial password guard missing'; END IF;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_local_update BEFORE UPDATE ON local_user FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    IF NOT (OLD.user_id <=> NEW.user_id) OR NOT (OLD.domain_id <=> NEW.domain_id) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Local user owner change forbidden'; END IF;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_local_delete BEFORE DELETE ON local_user FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard SET revision = revision + 1 WHERE user_id = OLD.user_id;
    IF ROW_COUNT() <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Initial password guard missing'; END IF;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_user_insert BEFORE INSERT ON `user` FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    INSERT INTO afterglow_password_guard(user_id, revision) VALUES(NEW.id, 1) ON DUPLICATE KEY UPDATE revision = revision + 1;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_user_update BEFORE UPDATE ON `user` FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    IF NOT (BINARY OLD.id <=> BINARY NEW.id) OR NOT (BINARY OLD.domain_id <=> BINARY NEW.domain_id) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'User owner change forbidden'; END IF;
    IF NOT (OLD.enabled <=> NEW.enabled) OR NOT (BINARY OLD.extra <=> BINARY NEW.extra) THEN
        UPDATE afterglow_password_guard SET revision = revision + 1 WHERE user_id = OLD.id;
        IF ROW_COUNT() <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Initial password guard missing'; END IF;
    END IF;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_user_delete BEFORE DELETE ON `user` FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard SET revision = revision + 1 WHERE user_id = OLD.id;
    IF ROW_COUNT() <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Initial password guard missing'; END IF;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_federated_insert BEFORE INSERT ON federated_user FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard SET revision = revision + 1 WHERE user_id = NEW.user_id;
    IF ROW_COUNT() <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Initial password guard missing'; END IF;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_federated_update BEFORE UPDATE ON federated_user FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    IF NOT (BINARY OLD.user_id <=> BINARY NEW.user_id) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Federated user owner change forbidden'; END IF;
    IF NOT (BINARY OLD.idp_id <=> BINARY NEW.idp_id) OR NOT (BINARY OLD.protocol_id <=> BINARY NEW.protocol_id) OR NOT (BINARY OLD.unique_id <=> BINARY NEW.unique_id) OR NOT (BINARY OLD.display_name <=> BINARY NEW.display_name) THEN
        UPDATE afterglow_password_guard SET revision = revision + 1 WHERE user_id = OLD.user_id;
        IF ROW_COUNT() <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Initial password guard missing'; END IF;
    END IF;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_federated_delete BEFORE DELETE ON federated_user FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard SET revision = revision + 1 WHERE user_id = OLD.user_id;
    IF ROW_COUNT() <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Initial password guard missing'; END IF;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_idp_update BEFORE UPDATE ON identity_provider FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard g JOIN federated_user f ON f.user_id = g.user_id SET g.revision = g.revision + 1 WHERE f.idp_id = OLD.id;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_idp_delete BEFORE DELETE ON identity_provider FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard g JOIN federated_user f ON f.user_id = g.user_id SET g.revision = g.revision + 1 WHERE f.idp_id = OLD.id;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_protocol_update BEFORE UPDATE ON federation_protocol FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard g JOIN federated_user f ON f.user_id = g.user_id SET g.revision = g.revision + 1 WHERE f.idp_id = OLD.idp_id AND f.protocol_id = OLD.id;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_protocol_delete BEFORE DELETE ON federation_protocol FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard g JOIN federated_user f ON f.user_id = g.user_id SET g.revision = g.revision + 1 WHERE f.idp_id = OLD.idp_id AND f.protocol_id = OLD.id;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_mapping_update BEFORE UPDATE ON mapping FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard g JOIN federated_user f ON f.user_id = g.user_id JOIN federation_protocol p ON p.idp_id = f.idp_id AND p.id = f.protocol_id SET g.revision = g.revision + 1 WHERE p.mapping_id = OLD.id;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_mapping_delete BEFORE DELETE ON mapping FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard g JOIN federated_user f ON f.user_id = g.user_id JOIN federation_protocol p ON p.idp_id = f.idp_id AND p.id = f.protocol_id SET g.revision = g.revision + 1 WHERE p.mapping_id = OLD.id;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_remote_insert BEFORE INSERT ON idp_remote_ids FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard g JOIN federated_user f ON f.user_id = g.user_id SET g.revision = g.revision + 1 WHERE f.idp_id = NEW.idp_id;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_remote_update BEFORE UPDATE ON idp_remote_ids FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard g JOIN federated_user f ON f.user_id = g.user_id SET g.revision = g.revision + 1 WHERE f.idp_id = OLD.idp_id OR f.idp_id = NEW.idp_id;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_remote_delete BEFORE DELETE ON idp_remote_ids FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard g JOIN federated_user f ON f.user_id = g.user_id SET g.revision = g.revision + 1 WHERE f.idp_id = OLD.idp_id;
END;
-- afterglow-statement
CREATE TRIGGER afterglow_mapping_insert BEFORE INSERT ON mapping FOR EACH ROW
BEGIN
    IF @@session.wsrep_on <> 1 OR @@session.foreign_key_checks <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsafe password writer session'; END IF;
    UPDATE afterglow_password_guard g JOIN federated_user f ON f.user_id = g.user_id JOIN federation_protocol p ON p.idp_id = f.idp_id AND p.id = f.protocol_id SET g.revision = g.revision + 1 WHERE p.mapping_id = NEW.id;
END;
