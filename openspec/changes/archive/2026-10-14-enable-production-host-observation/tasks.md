## Implementation Tasks

- [x] Confirm deployed topology-disabled root cause, native inventory, Ceph host identity, prerequisites and verified HTTPS access without changing production.
- [x] Back up protected operator inputs and target runtime config; prepare 18 host identities, bounded peer targets and least-privilege observer services using the released source and supported Python.
- [x] Enable connection-traffic analysis with independent backend and frontend writer secrets and verified proxy/address coverage.
- [x] Run canonical Afterglow-only Kolla genconfig, pull, prechecks and reconfigure with immutable existing images and preserved unrelated services/data.
- [x] Prove all configured host reports are fresh, NIC rates advance, admitted peer TCP results are observed, and observer services survive restarts.
- [x] Prove actual public HTTPS backend and frontend requests increment separate production aggregates; verify authenticated topology/traffic screens and security boundaries.
- [x] Record exact production evidence and limitations in existing deployment/architecture/changelog documents and archive this operation.

## Verification scope

Production native/browser proof, not fixtures: 18 fresh/rate-bearing hosts; 34 directed TCP up; all observers enabled/nonroot/cap0/seccomp with strict memory protection. Storage standalone executable required an official CPython-main noexec-stack rebuild; all three native thread/TCP/TLS smokes and post-restart reports passed without weakening sandbox or changing system Python.

Actual HTTPS request pairs increased backend /api/monitoring requests/2xx/body-known by12 and frontend /login requests/2xx/pageviews/body-known by3. Real admin topology and both traffic sources returned200; ordinary-user admin reads403; unauth/wrong/cross-host observer and writer/admin misuse401; valid writer invalid event422.

Combined observation smoke retained `passed:false` solely because ordinary logout returned503 (`Keystone revoke 실패 / Unauthorized`), although the refresh/JWT session was revoked and subsequent me returned401. Native Keystone token revocation is not verified; auth source/roles were not changed. Requested observation/traffic/authorization acceptance is recorded separately, never by re-pinning the failing logout expectation. GeoIP is unconfigured, frontend visitor identity unknown, optional LLDP/traceroute unsupported, and accumulated drops remain visible as partial coverage. No new app images, source gate, commit/push or unrelated service/data changes.

Architecture: an isolated frozen current-public-source clone, including unrelated concurrent WIP and the updated root ARCHITECTURE section, passed working stamp and staged guard `source_sha256=f679b834c71d82e01d8350b75630eb82cfd64ee9c65d2a4ba5afbcdea2802122` / 2864 files. Shared index and its review block were preserved. Production proof receipts are retained privately; secret values and tokens were never printed or committed.
