## 1. Scope and contracts

- [x] 1.1 Inspect the existing registry, caller authentication, credential issuance, OAuth and Lumen bridge; preserve prior shared changes.
- [x] 1.2 Define read-default Lumen delegation and immutable project/access contracts.

## 2. Server authority

- [x] 2.1 Add additive project metadata/credential storage and preserve old single-project grants.
- [x] 2.2 Implement authenticated project selection for personal keys, target-scoped issuance and complete cleanup/revocation.
- [x] 2.3 Implement OAuth access attenuation/project approval and preserve approved restrictions through exchange/refresh.
- [x] 2.4 Enforce target scope in project listing, tool schemas, preview/dispatch and mutation idempotency.

## 3. Default tools and user surfaces

- [x] 3.1 Lazily create a user/current-project read-only internal Lumen delegation before authorized tool-enabled chat; preserve explicit selected keys.
- [x] 3.2 Expose built-in cloud availability and compose it into the existing Lumen Tools menu without shared user credentials.
- [x] 3.3 Add read/manage and all/selected project controls and saved restrictions to personal-key and OAuth consent UI in four languages.

## 4. Verification

- [x] 4.1 Exercise changed API/MCP/SDK/plugin paths through actual local HTTP, including cross-user/project rejection, read/write restriction and OAuth refresh attenuation.
- [x] 4.2 Exercise the actual browser token/OAuth/Tools surfaces at responsive cutovers, themes and four locales; record synthetic boundaries.
- [x] 4.3 Run focused behavioral tests, relevant targets, diagnostics/localization checks and architecture validation; record exact outcomes and limits.
