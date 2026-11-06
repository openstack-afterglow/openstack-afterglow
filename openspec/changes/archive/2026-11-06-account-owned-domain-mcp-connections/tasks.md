## 1. Account inventory and authority
- [x] 1.1 Implement exact-user account-wide connection lists with saved issuance origin.
- [x] 1.2 Resolve stored origin for exact-user revocation while preserving project locks/audit/cleanup and runtime authority.
- [x] 1.3 Verify single-domain multi-project issuance and no foreign-user visibility.

## 2. Account interface
- [x] 2.1 Separate account connection inventory from workspace-dependent issuance/preview and route gating.
- [x] 2.2 Show saved origin/restrictions and preserve identity/ABA/secret fences.

## 3. Verification and documentation
- [x] 3.1 Run targeted backend/frontend regressions and relevant named targets.
- [x] 3.2 Exercise actual runtime/account browser flow, documenting synthetic/native boundaries.
- [x] 3.3 Update architecture and user/API/security documentation, validate/stamp, and archive the completed change.

Verification: MCP backend1406, auth backend1589, exact auth/key216, OAuth SQL132 and final account/navigation/mockup391 passed. Actual source browser→Uvicorn→MariaDB→installed SDK native cleanup denial proof retained under `~/.local/share/afterglow-proofs/account-mcp-inventory-20261106/`. Extended auth frontend971 passed/6 unrelated UI-selector failures; latest Svelte check has2 unrelated ImageRepositoryDetail errors/19warnings. Full gate/commit/push/deploy not performed. Details and limitations: `docs/testing.md`.
