## ADDED Requirements

### Requirement: Per-project operation consent
OAuth consent SHALL let the user choose, independently for each approved project, any non-empty subset of `read`, `create` and `update` operations, where `update` covers changing and deleting existing resources. Every MCP tool SHALL declare exactly one operation, and dispatch SHALL require that operation on the target project at target binding, mutation claim and final dispatch.

#### Scenario: Create without update
- **WHEN** a user approves `read` and `create` on project A
- **THEN** the client can list and create resources in A, and a change or delete tool on A is rejected before provider mutation

#### Scenario: Read not selected
- **WHEN** a user approves only `create` on project B
- **THEN** read tools targeting B are rejected and create tools targeting B are admitted

#### Scenario: Write on a read-only project
- **WHEN** approval requests `create` or `update` on a project where the user lacks a native write role, or the client did not request `mcp:write`
- **THEN** approval fails and no grant or credential is created

#### Scenario: Grant saved before per-project operations
- **WHEN** a stored grant project has no `operations`
- **THEN** it allows `read`, and also `create` and `update` only when the grant access level is `manage` and the project was writable at approval

### Requirement: Native policy actions without capability leaves
The system SHALL accept a Palimpsest policy response that carries only native `actions` and SHALL project those actions to Palimpsest capability leaves instead of reporting an invalid response.

#### Scenario: Palimpsest 0.3.13 or later
- **WHEN** Palimpsest returns `{"service": "palimpsest", "actions": [...]}` without `capabilities`
- **THEN** the preview and native permission checks use the leaves projected from those actions
