## Implementation Tasks

- [x] Confirm current enrollment/login/workspace contracts and define the home-first API/UI cutover.
- [x] Implement domain-free canonical password authentication, safe public provider options and home-first external session issuance; migrate backend consumers and behavioral regression coverage.
- [x] Remove domain-entry frontend flow, require fresh-login workspace selection and preserve onboarding/invitation/MCP/reauthentication/stale-response boundaries with localized UI and regression coverage.
- [x] Run related backend/frontend/contracts and isolated HTTP plus browser login→home→organization selection proof; record actual boundaries and failures.
- [x] Update architecture/design/API/auth/testing/changelog documentation and archive the completed change while preserving user state.
