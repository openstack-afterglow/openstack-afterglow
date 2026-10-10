## ADDED Requirements

### Requirement: Afterglow exposes Drover cluster reauthorization

The Drover BFF SHALL allow `GET /v1/clusters/{id}/authorization` with inventory authority, `POST /v1/clusters/{id}/authorization` with clusters-admin authority and the owner-scoped `POST /v1/clusters/{id}/authorization/retire`, and SHALL keep rejecting unknown authorization sub-routes. The project cluster page SHALL show when continuous cluster authority is missing, offer reauthorization only to a current clusters-admin on an ACTIVE cluster, report an in-progress generation until Drover activates it, and offer retirement only for the caller's own superseded credentials. Credential secrets SHALL never be requested or displayed.

#### Scenario: A legacy cluster has no resource authority
- **WHEN** a clusters-admin opens an ACTIVE cluster whose authorization status is not authorized
- **THEN** the page explains that Stampede, reconciliation and guest plugins are paused and offers reauthorization, which shows progress until Drover reports the new generation

#### Scenario: A reader without clusters-admin opens the cluster
- **WHEN** the caller can read the cluster but lacks clusters-admin
- **THEN** the missing-authority notice explains the required capability and offers no reauthorization action

#### Scenario: Stampede is refused for missing authority
- **WHEN** enabling Stampede returns Drover's refusal
- **THEN** the page shows the refusal reason instead of silently ignoring it

#### Scenario: Another user's superseded credentials remain
- **WHEN** the retirement backlog contains credentials owned by other users
- **THEN** the caller is offered retirement only for credentials they own
