## Implementation Tasks

- [x] Trace displayed OAuth client and project identifiers and preserve owner/revocation semantics.
- [x] Hide OAuth identifier values from card and confirmation; keep project names, permission and lifecycle metadata, and existing API-key behavior. Distinct visible ordinal labels identify removal targets while exact grant ID is preserved.
- [x] Verify multiple OAuth grants, exact revoke target, no identifier in DOM/dialog, responsive actual browser; update docs and archive. Frontend component tests and actual tutorial browser at390/1280 light/dark confirm masked IDs, ordinal and no overflow; two-grant/never-expiring revoke targeting covered by synthetic component tests. API continues returning identifiers; no production deployment.
