## Implementation Tasks

- [x] Derive the Hub HAProxy hostname from the configured public endpoint URL while retaining explicit exposure and hostname consistency checks.
- [x] Project the configured Hub endpoint into both Afterglow services TOML layers; retain operator TOML when no deployment URL is supplied.
- [x] Exercise real Ansible configuration rendering, precedence, disabled exposure, invalid origin rejection and local HAProxy HTTP routing.
- [x] Update affected deployment documentation, architecture review and sibling handoff; run related Kolla checks and archive this change.
