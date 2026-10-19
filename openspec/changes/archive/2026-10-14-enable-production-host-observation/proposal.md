## Why

The production infrastructure topology reports host observation disabled. The user also requests enabling the disabled connection-traffic analysis. Read-only runtime inspection confirmed Afterglow v1.30.16 has topology disabled, no observers or peers, and the protected backend operator TOML has no activation settings. Native inventory contains 12 compute nodes and 3 controllers; configured Ceph monitors resolve to three actual dms-storage nodes.

## What Changes

- Enable the existing topology and traffic-analytics contracts through protected Kolla operator inputs, keeping published application image digests, datastore targets, keys, inventory and unrelated services unchanged.
- Register a distinct random bearer identity for each of the 18 verified hosts; run the already released observer as a dedicated unprivileged systemd service with a 10-second interval and verified HTTPS.
- Provision an isolated supported Python runtime on Ubuntu 22.04 storage nodes without replacing system Python. Preserve truthful unsupported states for unavailable LLDP/traceroute tools; no firewall/NIC/cloud-resource changes or network scans.
- Admit bounded directed TCP checks only to existing node_exporter endpoints using verified inventory/Ceph address ownership. Do not infer physical links or reverse reachability.
- Enable backend request aggregation and protected frontend-server reporting with independent secrets. Client-address trust is enabled only if deployed proxy normalization and adapter behavior are proved; otherwise retain unknown-IP coverage. No fabricated geography.
- Back up operator inputs and target runtime config before applying the canonical genconfig/pull/prechecks/reconfigure sequence with only the Afterglow tag and existing immutable images. Exclude HAProxy regeneration because it is unrelated to activation and prior production receipts record LB image drift.

## Capabilities

### New Capabilities

None. This is activation of already published capabilities, not a new application release.

### Modified Capabilities

- Production Linux host observation and infrastructure-topology data collection.
- Production backend/frontend HTTP traffic aggregation.

## Impact

Protected configuration, per-host observer files/service users/units, isolated storage-node Python runtime, and existing Afterglow process configuration. No API/schema/dependency/public-default changes, no broad multi-service release, no credential disclosure and no datastore migrations. Finish with actual per-host report freshness, NIC rate/TCP observations, both traffic sources and real authenticated Chromium screens. Secret-bearing backups remain only on the operator; repository evidence contains nonsecret summaries.
