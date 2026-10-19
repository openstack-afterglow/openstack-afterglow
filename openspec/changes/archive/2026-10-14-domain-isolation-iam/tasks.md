## Implementation Tasks

- [x] 1. Enforce system:all admin authorization and remove project-admin compatibility inputs and UI.
- [x] 2. Add administrator domain inventory/creation and per-domain resource, service, request, login, session and user-activity monitoring with truthful availability.
- [x] 3. Scope administrator users, groups, projects and credentials to explicit domains; require domain-selected account creation and prevent cross-domain selections.
- [x] 4. Add user-console domain IAM for domain manager/admin: email invitations, password account creation, project roles and membership lifecycle with authoritative object/role boundaries.
- [x] 5. Implement domain-first login and domain-bound password/federated login, sessions, refresh, rescope, user inventories and frontend state.
- [x] 6. Implement durable domain password/OIDC/OAuth provider settings, encrypted secrets, login email allowlists and opt-in verified-email registration policies.
- [x] Verify security regression targets and real HTTP/SQL/Redis changed paths; exercise responsive four-locale UI with clearly labeled synthetic identity/provider boundaries; run project gate. Local scoped acceptance passed; full gate remains failed on 11 pre-existing unrelated storage tests (6,868 passed), with an unrelated Svelte type error reported separately.
- [x] Build affected declared container architectures, safely deploy canonical development services, verify health and actual changed runtime paths, and record operational prerequisites/compatibility limits. All affected image targets built/executed; canonical isolated Compose and native image processes passed. Real cloud/IdP/SMTP, VM boot and production/mixed-version/backup-restore qualification are not claimed; see docs/testing.md and verification.json.
