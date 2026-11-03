## Goal

Repair the live 1.32.5 MCP schema mismatch without replacing credentials, deleting grants, or extending existing consent. Add fail-closed SQL106 application to the canonical Kolla bootstrap path and publish/deploy 1.32.6.

## Tasks

- [x] Preserve a protected production MCP table backup; apply release-pinned SQL106 under explicit approval and verify original grant/token row hashes, all three API schema readbacks, and actual deployed list query/serialization (OAuth3/personal0). Authenticated HTTP/browser verification remains in the final deployment task; relay extension is unavailable.
- [x] Implement SQL106-only checksum-verified, idempotent schema bootstrap before new writers; verify real MariaDB migration, repeat invocation and failure propagation.
- [x] Update architecture/deployment/testing/changelog and version metadata to 1.32.6; preserve unrelated checkout/index changes.
- [x] Run exact selectors, runtime migration smoke and the full canonical test gate; review release changes.
- [x] Push dev, verify exact-SHA CI, publish immutable numeric 1.32.6 tag, bilingual GitHub Release, release images/aliases and Helm.
- [x] Verify live schema/cohort/config preservation and actual authenticated MCP list HTTP200; close deployment acceptance using the independently completed addon rollout's SQL106 bootstrap/failed0 recap and observed exact1.32.6 cohort, without duplicate control restarts. Record own compute SSH255/no recap, the other full deploy.exit2, and unavailable visual browser relay as explicit residuals rather than claiming an infrastructure-wide successful reconfigure.
