-- Several delegated grants may be enabled for Lumen per owner/project.
-- The primary key now includes grant_id. Existing rows (at most one per owner/project)
-- remain valid and keep their meaning: that grant is the owner's only enabled Lumen grant.
ALTER TABLE mcp_lumen_selections DROP PRIMARY KEY, ADD PRIMARY KEY (owner_user_id, owner_project_id, grant_id);
