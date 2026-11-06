## Why
Publish the user's current reviewed Afterglow changes as the explicitly requested patch version 1.32.9, including account-owned MCP inventory and the completed current UI/instance-safety changes.

## What Changes
- Freeze the current public working snapshot; exclude later concurrent changes and ignored private inputs.
- Synchronize canonical 1.32.9 version metadata and record the delta from immutable 1.32.8.
- Run the required complete gate and real runtime smoke; fix only demonstrated release blockers.
- Commit on shared dev, push normally, require exact-SHA CI success, then publish immutable numeric tag, bilingual release, images/aliases and Helm.

## Capabilities
### New Capabilities
None beyond the frozen existing changes.
### Modified Capabilities
Release qualification and artifact version only.

## Impact
No production deployment, native role/schema changes, existing-tag movement, main merge, force push or unrelated secret/configuration inclusion. Preserve shared checkout/index and concurrent work.

## Verification and Publication
- Qualified source SHA256: `73d5f8c0f9a431a6e4c8a931afee2ae72a4a1478cf460a65502972db730c5dbe` (4,172 files). Complete canonical gate: 14,511 backend, 7,593 frontend, 261 contract and 283 functional passes; Ruff879, production build, Svelte0errors/15existing warnings, i18n/scan0errors and staged Gitleaks0 findings.
- Shared-dev integration: 48 backend and 163 frontend regression passes. Exact source commit and immutable tag target: `dcf1c4b9d04b23af76aadbc0d065dff70f147808` / `1.32.9`.
- Exact dev CI42245065818, tag image CI42246620078 and Helm CI42246620088 succeeded. The bilingual GitHub Release body was read back exactly.
- All three GHCR1.32.9/latest pairs have identical digests and the exact source revision, declaring linux/amd64. Pinned API/worker/frontend image version commands reported1.32.9; these do not prove full API/worker startup. Canonical published frontend Node20 image browser smoke verified regex errors, sorting/refresh and390px compact controls with synthetic tutorial data.
- Helm OCI1.32.9 was pulled and checked for version/appVersion1.32.9. Detailed digests, limits and receipts are recorded in `docs/testing.md` and `~/.local/share/afterglow-proofs/release-1329-20261106/qualification.json`. No main merge, production rollout, native schedule write or Helm installation was performed.
