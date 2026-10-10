## ADDED Requirements

### Requirement: Built-in user-scoped resource tools
Lumen SHALL provide default cloud resource inspection and monitoring through the existing MCP registry without a manually created personal token or a shared cloud credential. Default delegation SHALL be read-only and fixed to the authenticated user's current project.

#### Scenario: First authenticated tool-enabled chat
- **WHEN** an authorized user sends a native text-chat request with tools enabled
- **THEN** the server ensures that user's current-project read delegation and Lumen receives its opaque snapshot and real resource tool catalogue

#### Scenario: Isolation and stale authority
- **WHEN** another user/project requests tools or a frozen grant is expired/revoked/replaced
- **THEN** authority is resolved separately and stale execution is rejected before cloud I/O

#### Scenario: Existing explicit delegation
- **WHEN** a dispatchable personal delegation is already selected
- **THEN** the default setup preserves that explicit grant and its approved restrictions

#### Scenario: Disabled or denied tools
- **WHEN** tool policy is none, MCP is disabled, or the current user lacks the Lumen tools capability
- **THEN** no automatic cloud delegation is created
