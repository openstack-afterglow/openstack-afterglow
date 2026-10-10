## ADDED Requirements

### Requirement: Selected parents project actual inherited permissions
The project member role editor SHALL use the existing server-validated role-ID transitive closure to display descendants of selected direct parents as checked and read-only. It SHALL NOT infer authority from role names, grades or a default preset. Removing a parent SHALL recompute descendant state without deleting existing explicit direct child grants, shared-parent inheritance or externally inherited authority.

#### Scenario: A direct parent is selected
- **WHEN** the operator selects a direct role whose current trusted metadata contains descendant role IDs
- **THEN** every visible descendant is checked and cannot be separately toggled
- **AND** those descendants are not automatically added to the direct-role save payload

#### Scenario: A parent is removed
- **WHEN** the operator removes one selected parent
- **THEN** descendants no longer implied by any remaining parent become editable
- **AND** explicitly selected direct descendants remain selected
- **AND** descendants still implied by another selected parent remain checked and read-only

#### Scenario: Authority is inherited outside direct selection
- **WHEN** the current group/domain inherited assignment rows grant roles to the member, whether or not those roles are also implied by an original direct parent
- **THEN** that external authority remains checked and read-only after direct parent changes
- **AND** it is not converted to a direct grant

#### Scenario: Direct and external grants overlap
- **WHEN** a direct parent and a group/domain inherited assignment both grant the same descendant and the operator removes that direct parent
- **THEN** the descendant and its trusted descendants remain checked and read-only from independently expanded `external_role_ids`
- **AND** the server preserves those external IDs after the direct-role replacement without changing the external assignment
- **AND** the client SHALL NOT infer external authority by subtracting the original direct-role closure from merged effective IDs

### Requirement: Search is independent of pending direct grants
The editor SHALL filter role name, exact ID and optional description using a trimmed case-insensitive query. Filtering SHALL preserve all pending direct-role selections, including roles hidden by the current query. Search and empty-result feedback SHALL have localized accessible labels in the supported UI languages.

#### Scenario: A selected role is hidden by a query
- **WHEN** a direct role is selected and a query hides it
- **THEN** clearing or changing the query restores its selected state
- **AND** saving still submits its original role ID rather than a visible-only subset

#### Scenario: A query has no matching roles
- **WHEN** no role name, ID or description matches the query
- **THEN** the editor presents an accessible localized empty-result status
- **AND** existing selections remain unchanged

### Requirement: Existing mutation and preservation boundaries remain enforced
The editor SHALL submit only the selected direct IDs and preserve original uneditable or unknown direct assignments without destructive normalization. Nonowners SHALL NOT toggle protected project owner/admin roles. Group-only or inherited-only membership SHALL remain noneditable, and busy state SHALL prevent checkbox mutation and saving. Cancel SHALL discard unsaved UI changes without issuing a role mutation; backend owner and authorization protections SHALL remain authoritative.

#### Scenario: A protected or busy control is used
- **WHEN** the actor is a nonowner targeting a protected owner/admin role, the membership is not directly editable, or a mutation is busy
- **THEN** the corresponding checkbox cannot change selection
- **AND** noneditable membership or busy state prevents saving

#### Scenario: Direct selection is saved or cancelled
- **WHEN** the operator saves editable direct selection
- **THEN** the callback receives direct role IDs only, including retained hidden or original uneditable assignments
- **WHEN** the operator cancels instead
- **THEN** no role mutation is issued
