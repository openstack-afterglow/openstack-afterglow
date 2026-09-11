## Why

Afterglow requests routed to controller3 repeatedly reached the browser's 30-second timeout while identical requests through controller1/2 completed. Production logs showed continuous Keystone discovery failures only on controller3. The host resolved the internal Keystone FQDN to its public address because its resolver omitted the internal DNS server, while the other controllers resolved the same name to the Kolla VIP.

## What Changes

- Repair controller3's persistent `systemd-resolved` configuration to use the internal DNS server, preserving a timestamped backup.
- Add an Afterglow Kolla precheck that performs an HTTPS request to the configured internal Keystone URL from every enabled Afterglow host.
- Keep the check read-only, certificate-aware, and bounded by a ten-second timeout.
- Add contract coverage proving the check is per-host rather than `run_once` or delegated.

## Impact

No application architecture change. The live DNS repair removes the current intermittent timeout, while the Kolla precheck prevents future multi-controller deployments from admitting a backend host that cannot resolve or reach Keystone correctly.
