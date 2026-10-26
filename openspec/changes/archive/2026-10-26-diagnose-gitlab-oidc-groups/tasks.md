## Implementation Tasks

- [x] Read GitLab/Keystone references, actual public provider discovery, current OIDC forwarding/mapping source and development rules; distinguish evidence boundaries.
- [x] Define an isolated loopback callback, browser/token validation, least-scope new client setup, and secret-free diagnostic/report contract.
- [x] Implement the standalone probe, exact group-source reports, explicit candidate mapping export and private output handling without changing application authentication/configuration.
- [x] Add deterministic consumer-visible regression coverage for callback binding/replay, verified JWT/UserInfo identity, missing/empty/malformed group claims, endpoint binding, and secret-free outputs.
- [x] Exercise the actual CLI/callback against a signed synthetic HTTP provider; document exact proof and remaining new-client/human-login acceptance.
- [x] Update operator/auth/architecture/changelog documentation, run relevant validation and isolated architecture freshness checks, and prepare this tool-delivery change for archive. Focused140 and backend auth1119 passed; adjacent frontend auth634 passed/2 unrelated navigation failures recorded. Full gate and new-client human/native acceptance are not claimed.
