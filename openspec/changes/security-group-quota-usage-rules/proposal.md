## Why

The project security-group screen cannot show Neutron group/rule quota or which VMs use a group. Rule creation hides above the table and silently omits the remote CIDR; the existing rule list mislabels group-targeted or IPv6 rules as open IPv4. Operators cannot safely reuse rule settings when Neutron requires delete-and-create rather than editing a rule.
The administrator project quota editor currently exposes only instance/CPU/RAM, volume count/capacity, and GPU settings. It cannot set Cinder snapshots, Neutron resources including the group/rule limits shown to users, or Manila share/network/group/snapshot limits. Missing data must not be presented as editable zero quotas.

## What Changes

- Expose project-scoped security-group and security-group-rule quota limits/usage, and instances attached through compute ports, on authenticated read endpoints. Do not substitute fabricated zero quota or leak another project's ports/servers.
- Extend rule creation with an optional project-owned remote security group; make remote CIDR and remote group mutually exclusive. An omitted CIDR defaults to the selected IP family's open network, and an omitted end port equals the start port.
- Show quota and attached VMs on the user security-group screen. Place the creation form inside the rule table (including the empty-table state), select between CIDR/group targets, show the actual selected group and an explicit IPv4/IPv6 column per rule, and explain the port default. Copy an existing rule into the inline form for deliberate remove-and-recreate; never claim an atomic in-place Neutron edit.
- Expand the admin project quota API and form with Nova compute fields, Cinder volume/snapshot/total capacity, Neutron network/subnet/port/router/FIP/group/rule, and Manila share/size/snapshot/snapshot-size/share-network/share-group/group-snapshot limits. Read per-service usage without fabricated zeros; omit/disable unavailable fields. Each UI save sends only that service's changed fields, preserving existing GPU management. Explicitly report partial multi-service API writes.
- Document API and architecture, cover permissions and consumer-visible edge cases, and verify actual UI/API behavior locally.

## Capabilities

### New Capabilities

- Project operators can see the number and limit of security groups and rules and identify instances whose ports attach the selected group.
- Rule targeting can use either CIDR or an existing security group in the same project.
- Administrators can read and set the requested project quota fields across Nova, Cinder, Neutron and enabled Manila without changing other services' quotas.

### Modified Capabilities

- Empty CIDR and end-port inputs have visible, consistent defaults; rule creation and replacement are part of the rule table, which identifies each rule's IP version.
- The admin quota page gains independent compute, volume, network and share sections with service-aware loading, validation and save feedback.

## Impact

FastAPI security-group and admin quota routes, Neutron/Manila read adapters, project-scoped Svelte security-group and admin quota screens/types, backend and frontend regression coverage, bilingual API docs, architecture and changelog. No database migration. Missing service quota usage is never treated as zero; no production/OpenStack claim without live access.
