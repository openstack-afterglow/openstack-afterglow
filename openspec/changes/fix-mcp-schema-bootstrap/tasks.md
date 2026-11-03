## Goal

Repair the live 1.32.5 MCP schema mismatch without replacing credentials, deleting grants, or extending existing consent. Add fail-closed SQL106 application to the canonical Kolla bootstrap path and publish/deploy 1.32.6.

## Tasks

- [x] Preserve a protected production MCP table backup; apply release-pinned SQL106 under explicit approval and verify original grant/token row hashes, all three API schema readbacks, and actual deployed list query/serialization (OAuth3/personal0). Authenticated HTTP/browser verification remains in the final deployment task; relay extension is unavailable.
- [x] Implement SQL106-only checksum-verified, idempotent schema bootstrap before new writers; verify real MariaDB migration, repeat invocation and failure propagation.
- [x] Update architecture/deployment/testing/changelog and version metadata to 1.32.6; preserve unrelated checkout/index changes.
- [x] Run exact selectors, runtime migration smoke and the full canonical test gate; review release changes.
- [ ] Push dev, verify exact-SHA CI, publish immutable numeric 1.32.6 tag, bilingual GitHub Release, release images/aliases and Helm.
- [ ] Deploy through the approved complete compute/control Kolla commands, verify schema/cohort/config preservation and actual MCP page, then archive this change.
