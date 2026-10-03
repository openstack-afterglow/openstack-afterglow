## ADDED Requirements

### Requirement: Attached network identity is legible and project-scoped
The Afterglow Waygate workspace SHALL display project-visible attached network names while retaining immutable network IDs as attachment identities and fallbacks. A catalog lookup failure SHALL NOT hide attachments or enable cross-project network resolution.

#### Scenario: Named attachment and missing catalog entry
- **WHEN** the selected project's network catalog contains one attached network and omits another
- **THEN** the first attachment displays its network name, the second displays its network ID, and detach sends the original attachment ID

### Requirement: Peer and metadata refresh remain independent
The visible Waygate workspace SHALL offer a separate peer refresh control with Off, 1, 2, 5, 10, 15, 30 and 60 seconds, alongside the existing server/network metadata refresh. Peer polling SHALL await the previous request, stop while hidden or without a project/server, discard responses from old server/project/auth scopes, and use a monotonic generation after a client mutation so an older poll cannot replace fresh data. The dashboard SHALL distinguish disabled, unknown, and delayed reports by receipt age using the larger of 5 seconds or three times the greater of the selected peer cadence and reported agent interval; missing interval metadata from legacy agents SHALL remain unknown rather than pretending it is one second.

#### Scenario: Turn off live peer refresh
- **WHEN** a member selects Off for peer refresh while keeping metadata refresh enabled
- **THEN** peer requests stop without stopping the metadata timer or discarding already displayed server and network information

#### Scenario: Stale response after a mutation or scope change
- **WHEN** a slow peer request begins, then the member edits a client or switches server/project before it returns
- **THEN** a fresh scoped request wins and the old response cannot overwrite the new settings, peer counters, or traffic history

### Requirement: Client actions stay reachable and stable
Every client row SHALL show the same download, QR, and settings icon actions in that order, followed by a divider, a labeled enabled toggle and delete action. Each icon SHALL have a discernible accessible label and keyboard focus; mobile touch targets SHALL be at least 44px. Detach confirmation SHALL retain the immutable network UUID even when a network name is resolved.

#### Scenario: Resolve duplicate network names
- **WHEN** two attached networks share a name in the project catalog
- **THEN** each attachment and its detach confirmation expose its own UUID and detach still uses the selected attachment ID


### Requirement: Peer reports use one agent and two deadlines
A single long-lived sequential gateway agent SHALL reconcile desired peers/NAT every 15 seconds and independently sample `wg show` and POST status at an operator-configurable interval of 1–60 seconds, default 1 second. It SHALL reload durable bearer state without concurrent writers, skip missed monotonic deadlines without catch-up bursts, and report the actual configured sampling interval. Cloud-init and prebuilt installations SHALL install the same service without a recurring timer. Status responses SHALL preserve server receipt timestamps and five-minute observational cache TTL; failed samples SHALL NOT publish empty peers as fresh observations.

#### Scenario: Traffic between reconciliations
- **WHEN** unchanged desired state and a connected peer transfers bytes across three status deadlines
- **THEN** successive gateway counter reports advance without fetching desired state or rewriting NAT at each report deadline

#### Scenario: Slow reconciliation
- **WHEN** the sequential reconciliation takes longer than one report interval
- **THEN** reports may be delayed but no parallel token writer or backlog of catch-up requests starts

### Requirement: Server defaults dynamically apply to inheriting clients
Waygate SHALL persist project-owned server DNS and strict integer 0–65535 keepalive defaults, and client boolean `inherit_dns` and `inherit_persistent_keepalive` flags. Existing clients SHALL migrate with flags false and unchanged values/configurations/keys; a new client whose field and flag are both omitted SHALL inherit. Explicit DNS null and keepalive zero SHALL remain overrides. Client list/create/PATCH SHALL return effective values with flags; `.conf` rendering and export SHALL use the same resolver. MTU remains individually stored and editable, not a new server default.

#### Scenario: Distinct inherited and explicit peers
- **WHEN** a server's DNS and keepalive defaults change after one inheriting and one explicit-null/zero client were issued
- **THEN** the inheriting client's list, downloaded configuration and QR use new defaults, while the explicit client's DNS remains absent and keepalive remains zero without changing its private key/PSK

#### Scenario: Explicit inheritance transitions
- **WHEN** a client PATCH sets `inherit_dns:true` or `inherit_persistent_keepalive:true` without a value
- **THEN** the corresponding override is cleared and effective server defaults apply

#### Scenario: Invalid mode or owner
- **WHEN** a flag is null, flag=false has no value, flag=true accompanies a value, an integer field is a boolean or out of range, DNS contains a newline, or a caller PATCHes a different project's server
- **THEN** Waygate returns a validation error or owner-safe 404 without changing settings

#### Scenario: Defaults cannot change after deletion begins
- **WHEN** an owning member PATCHes defaults on a DELETING server, or a concurrent delete reaches the same parent-row lock first
- **THEN** the settings update returns 409 without changing the persisted values; a non-owner receives 404

#### Scenario: Export to a different server
- **WHEN** an inheriting client is exported and imported into a server with different defaults
- **THEN** the source effective DNS/keepalive and existing client keys/PSK are preserved as explicit overrides without changing the destination server defaults
