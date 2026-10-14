## ADDED Requirements

### Requirement: Explicit ownership of every background process
The system SHALL classify each background process as an assigned shared role, an assigned target worker, an authoritative broker/SQL competing consumer, or explicitly process/node/request-local work. Shared resource polling and mutations SHALL NOT execute independently on every controller.

#### Scenario: Three eligible replicas
- **WHEN** three processes participate against the same coordination and authority stores
- **THEN** shared roles or independent targets are divided among eligible participants
- **AND** a target's current work is owned by at most one valid execution lease.

#### Scenario: Required local state
- **WHEN** a process initializes its GPU catalog/cache or owns a live request, websocket or node agent
- **THEN** that local work remains in the process that requires it and is documented as local rather than omitted from the inventory.

### Requirement: Leader-only target discovery and independent execution
The system SHALL allow only the current fenced scheduling leader to discover shared target registries. Membership heartbeats and scheduling SHALL continue independently from slow provider calls.

#### Scenario: Blocked provider response
- **WHEN** a leader is also executing a blocked target operation
- **THEN** its heartbeat and discovery/assignment continue and other participants execute their own targets.

### Requirement: Revocation and failure handoff
Every participation incarnation SHALL fail closed after coordination loss. Assignment/lease validity SHALL be checked before new background mutations. Current SDK work SHALL drain before releasing its owned lease or connection; a crashed participant's work SHALL be eligible only after the applicable leases expire.

#### Scenario: Controller exits or crashes
- **WHEN** a role or target owner disappears
- **THEN** survivors receive its work without bypassing the remaining execution lease
- **AND** a returning process joins with a new incarnation.

#### Scenario: Delayed claim reply
- **WHEN** a Redis claim reply arrives after membership was lost
- **THEN** no new provider operation starts from that claim and its lease is left to fenced release or expiry.

### Requirement: Durable mutation and queue authority
Ready queues SHALL be rebuildable hints. Persistent policy/SQL/journal data SHALL remain authoritative. Broker/SQL queue consumers SHALL retain their atomic claim, commit/ack and recovery semantics. A provider-accepted or outcome-unknown mutation SHALL NOT be blindly replayed after controller failure.

#### Scenario: Accepted response is lost
- **WHEN** a backup or build create was accepted but the owner loses the response or exits
- **THEN** a durable unknown record prevents a second submission and recovery observes the exact existing provider identity.

#### Scenario: Work admitted on another replica
- **WHEN** an API replica admits durable library/import work and another worker owns its target
- **THEN** the owner can consume the recorded work without relying on the admitting replica's memory.

#### Scenario: Cancelled build with an unsettled create
- **WHEN** an administrator cancels a build whose provider create may still be accepted
- **THEN** the cancelled record stays pending until an assigned owner removes the exact journaled or uniquely tagged transient resources
- **AND** that cleanup owner submits no new provider create.

### Requirement: Service-scoped coordination prerequisites
All replicas of a workload SHALL share its service Redis primary, logical DB, namespace and durable authority stores, and participate in the same upgraded protocol. The system SHALL document per-process allocation and SHALL NOT claim duplicate prevention after coordination-data loss or successful production qualification from synthetic local evidence.

#### Scenario: Coordination unavailable
- **WHEN** Redis membership/assignment/lease cannot be verified
- **THEN** the worker starts no new shared operation and rejoins only with a fresh incarnation after recovery.
