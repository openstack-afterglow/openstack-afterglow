## ADDED Requirements

### Requirement: Administrator authority and provider execution
Every `/api/v1/admin` route SHALL depend on fresh system:all administrator authority, and provider reads SHALL use the verified configured admin-project connection rather than system-scoped tokens, which the native Nova, Glance, Neutron, Placement and RGW policies of this deployment reject or answer incompletely. Exceptions SHALL be enumerated in the route authority regression test with reasons.

#### Scenario: New admin route
- **WHEN** an admin route is added without the fresh administrator dependency
- **THEN** the route authority regression test fails

#### Scenario: Swift overview partial visibility
- **WHEN** some Swift accounts answer 401/403 to the admin-project connection
- **THEN** the overview reports the readable container total and the unreadable account count without marking the whole section unavailable
