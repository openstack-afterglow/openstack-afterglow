## ADDED Requirements

### Requirement: Sibling tenant execution never uses a tenant-scoped service password

Drover, Waygate and Palimpsest SHALL execute tenant OpenStack mutations only with authority delegated by the current requester (an operation-bound Keystone Trust or, for Drover continuous cluster work, a current user's restricted application credential). Their service identities SHALL authenticate only in their own service projects, and Afterglow SHALL forward the caller's validated project token so the sibling service can create that delegation.

#### Scenario: A system administrator acts on a project without a role there
- **WHEN** a verified system administrator uses the home-token override to request a sibling-service mutation in a project where they hold no role
- **THEN** the sibling service cannot rescope the token or create a Trust and the mutation fails closed without any service-identity fallback

#### Scenario: Authority is revoked after admission
- **WHEN** the requester loses the action capability, membership or Trust after a job was admitted
- **THEN** the next delegated cloud request is denied and the job fails without creating resources through another identity

### Requirement: Drover provisions natively behind Afterglow GPU admission

Afterglow SHALL NOT execute Nova or Cinder creates on Drover's behalf. Its internal K3s API SHALL provide GPU admission decisions only, and Drover SHALL re-check admission immediately before each GPU node create.

#### Scenario: A legacy Drover still calls the removed intent API
- **WHEN** a client requests `/api/v1/internal/k3s/provisioning-intents`
- **THEN** no route exists and no Afterglow service credential creates a server or volume

#### Scenario: GPU quota is exhausted between enqueue and create
- **WHEN** Drover re-checks GPU admission immediately before a GPU node create and Afterglow denies it
- **THEN** Drover creates no volume or server for that node
