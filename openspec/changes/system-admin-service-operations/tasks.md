## 1. Native authority

- [x] 1.1 Lumen: current system administrator alternative with zero target roles/membership, final revocation and credential attenuation. Final1,216 regressions,96 SQL tests and29 actual main-app HTTP checks recorded in docs/testing.md.
- [x] 1.2 Drover: human administrator target authorization and real dedicated executor-backed create/delete/credential lifecycle, original requester audit and worker revocation. Final460 regressions plus installed-SDK HTTP/executor smoke.
- [x] 1.3 Waygate: human administrator target authorization and real dedicated executor-backed provider operations, original requester audit and worker revocation. Final1,371passed/2skipped plus actual SDK/SQLite/worker lifecycle smoke.
- [x] 1.4 Palimpsest: human system administrator package/layer/build management with zero target membership, bounded machine credentials and target namespace safety. Final485passed/2skipped and49HTTP checks; build worker/live IAM not exercised.

## 2. Browser and BFF integration

- [x] 2.1 Afterglow: fresh system authority, enabled selected-domain target and separate caller/target headers for all four services.
- [x] 2.2 Administrator UI: preserve server-derived permission and stale-response fences while enabling selected-target management without service leaves.
- [x] 2.3 Native executor configuration/examples/generators and migration/writer compatibility documented and validated where changed. Drover005/Waygate007 and Palimpsest offline bootstrap exercised on owned MariaDB; production snapshot/mixed-version qualification remains a deployment prerequisite.

## 3. Verification and record

- [x] 3.1 Run precise authority/CRUD regression selectors and bounded real HTTP/native SDK smoke, including revocation, outages and ordinary principal isolation.
- [ ] 3.2 Verify actual administrator browser surfaces and full required gates without using shared Docker/external DB or live IAM.
- [x] 3.3 Update architecture, API/security/testing docs and changelog with exercised evidence and remaining deployment prerequisites.
  - Native tests, real HTTP/SQL, schema results and failed full-contract/image attempts are recorded in docs/testing.md. Canonical scoped architecture checks passed in five isolated dev clones without changing original indexes/shared review stamps; no deployment/green full-gate claim.
- [ ] 3.4 Validate OpenSpec, archive only after all requested behavior and verification is complete.
  - Strict OpenSpec validation passed for the current change artifacts; archive remains blocked by the qualification items below.

### Remaining qualification blockers

- 3.2: actual administrator surfaces passed; whole Svelte check retains2 recorded errors outside the feature. Lumen full contract remains unsuccessful (approval-checkpoint resume plus runner failures; tooling repair checks recorded separately). No fabricated full-green aggregate.
- Canonical native arm64/amd64 image attempts with RUN network disabled cannot acquire uncached Debian packages. Dependent runtime targets and local image deployment remain unqualified; no network/trust/dependency-policy relaxation or operator deployment.
- 3.4: keep this change open until required gates and image qualification are actually resolved. Local source/HTTP/SQL completion is not archive/release/deployment acceptance.

