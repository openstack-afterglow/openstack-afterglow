## ADDED Requirements

### Requirement: Evidence-based administrator layer inventory
The system SHALL provide a read-only administrator inventory of Afterglow-managed layers and native Palimpsest Hub layers without substituting service credentials for the current human administrator. Managed inventory SHALL remain independently available when Hub is unavailable. Creation provenance SHALL be recorded only from a completed build or import/export output tied to the exact layer; absent evidence SHALL remain unknown.

#### Scenario: Inspect a recorded build and its ancestry
- **WHEN** an authorized administrator selects a layer with an exact completed build receipt
- **THEN** the inventory displays the recorded origin, full digest, direct parent, root-to-parent ancestors and bounded direct children
- **AND** existing build studio, historical jobs and profile controls remain reachable

#### Scenario: Inspect a layer without creation evidence
- **WHEN** a visible layer has no exact durable creation receipt
- **THEN** its provenance remains unknown or unrecorded rather than being classified as imported

#### Scenario: Read global inventory without a selected project
- **WHEN** a freshly verified human system administrator performs GET on the exact administrator catalog list or detail route with an empty logical project
- **THEN** the request does not fabricate a project target
- **AND** consumer/package routes, neighboring routes and non-GET methods retain their project requirements

### Requirement: Authorized named asset discovery
The consumer dashboard SHALL search authorized native public/shared assets, current-project private package names/tags and published managed cloud environments as distinct sources. Search SHALL use server-side queries and bounded pagination. Candidate pages MAY contain no accessible complete assets while retaining continuation; the UI SHALL distinguish this from a completed empty result.

#### Scenario: A source fails independently
- **WHEN** Hub search is unavailable and private-package and managed-environment reads succeed
- **THEN** the dashboard retains the successful results and offers a Hub-only retry
- **AND** it does not present the failed source as an empty inventory

#### Scenario: Hidden chains fill a candidate page
- **WHEN** a bounded candidate page contains no accessible complete bundles and has a next offset
- **THEN** the response retains that continuation without disclosing hidden chain names
- **AND** the dashboard explains that this page has no usable bundle and keeps the next-page action enabled

### Requirement: Exact and supported local use
Local-use instructions SHALL identify the selected immutable digest, use supported public CLI verbs and stop after an acquisition or unpack failure. A complete chain SHALL NOT imply local runtime compatibility without a visible supported boot base and compatible architecture. Browser transfers SHALL be bounded to 64 MiB; larger assets SHALL use the CLI path. New unpack instructions SHALL require explicit confirmation that the installed client supports the command, without claiming that published client0.3.5 includes it.

#### Scenario: Select a private runtime bundle
- **WHEN** the caller selects a listed private runtime-bundle version and acknowledges installed unpack capability
- **THEN** acquisition, unpack and run commands refer to the exact selected digest and digest-derived paths
- **AND** the commands are joined conditionally so a failed earlier step cannot run an old output

#### Scenario: Select a chain without a runnable base
- **WHEN** an authorized asset lacks a supported boot base or compatible architecture
- **THEN** it remains discoverable but no executable local-use command or incompatible browser download is offered

### Requirement: Caller-owned immutable cloud consumption
The system SHALL revalidate current membership, native action authority, caller quota and the exact published sealed environment revision before cloud allocation. Compute resources SHALL belong to the caller project; the service connection SHALL be limited to source-share authorization. Acceptance SHALL return promptly with a durable operation identifier and SHALL NOT imply guest readiness. Uncertain creates SHALL NOT be blindly replayed.

#### Scenario: Publication is withdrawn during admission
- **WHEN** a transaction withdraws ancestor publication while consume admission waits for the same SQL row authority
- **THEN** admission observes the withdrawal after the lock is released and rejects with409
- **AND** it creates no consume row

#### Scenario: A pending operation outlives a tab change
- **WHEN** a create request is accepted or has an uncertain outcome and the user switches workspace tabs or rotates the verified token in the same logical session
- **THEN** the operation receipt and duplicate-create lock remain
- **AND** accepted and ready are displayed as different states

### Requirement: Exact cleanup and deletion ownership proof
All relevant ordinary, bulk, administrator and MCP VM deletion paths SHALL consult initialized readable durable LayerConsume ownership receipts before excluding catalog ownership, even when mutable native metadata omits the marker. Missing ownership authority SHALL fail closed. Cleanup SHALL release artifact blockers only after exact server and journaled dependent-resource absence is confirmed.

#### Scenario: Ownership SQL is unavailable
- **WHEN** a VM deletion cannot read its LayerConsume receipt authority
- **THEN** the request fails with503 without ordinary-delete fallback or provider deletion

#### Scenario: A known catalog marker is removed or mismatched
- **WHEN** an owned VM has a durable catalog receipt but its native marker is missing or mismatched
- **THEN** deletion fails with409 rather than bypassing catalog cleanup

#### Scenario: A foreign caller requests deletion
- **WHEN** the caller does not own the native VM or the exact receipt
- **THEN** the request returns404 without revealing or mutating the foreign resource

#### Scenario: Cleanup completes
- **WHEN** exact service-share grants and caller-owned server, floating IP, port and upper storage have confirmed cleanup outcomes
- **THEN** the operation may become deleted and release its artifact blockers
- **AND** an uncertain create or delete remains fenced until exact ownership and absence can be observed
