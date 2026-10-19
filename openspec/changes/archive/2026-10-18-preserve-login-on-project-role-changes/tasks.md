## Implementation Tasks

- [x] Trace blanket role-driven family revocation and native scoped-token coupling; obtain explicit user choice of login continuity with current-permission enforcement.
- [x] Preserve a caller-owned unscoped native login credential across login, access validation, refresh and scope transitions; never persist a derived project credential as the login proof.
- [x] Replace role-driven login-family deletion with fresh permission/token-cache invalidation across direct/group assignments, project role replacement and related manager projections; preserve explicit security revocation.
- [x] Cover self-role grant/reduction, fresh denied/allowed requests, refresh/rotation, cross-project isolation and explicit logout/credential invalidation with consumer-visible regressions.
- [x] Exercise actual HTTP authentication → role edit → subsequent authorized/denied request → refresh/logout with a disposable native Keystone fixture, and run focused plus named auth/access targets.
- [x] Update affected API docs, changelog and architecture review; record executed checks and limits and archive this change.
