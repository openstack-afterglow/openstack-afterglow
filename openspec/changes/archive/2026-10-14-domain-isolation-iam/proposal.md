## Why

All users currently operate through Default-oriented authentication and global Identity pages. Tenant domain management must not confer system-administrator privileges. The requested isolation covers login, session/rescope, identity management, credentials, and monitoring rather than a UI-only filter.

## What Changes

1. Remove project-admin compatibility authorization; only verified Keystone system:all admin grants authorize platform administration.
2. Add system-admin domain inventory and domain resource/service/request/login/session/activity observations. Unknown, unavailable, partial, disabled and measured-zero remain distinct; valid sessions are not asserted to be online.
3. Require explicit domains for administrative user creation; scope users, groups, projects and credential metadata queries, selections and cache publication to the chosen domain.
4. Add tenant IAM in the user console for verified domain manager/admin (and system admins), with email invitation, password-based account creation, project membership and role administration. All object IDs must belong to the authorized domain; project-owner and service-role ceilings remain enforced.
5. Resolve an enabled domain before login; offer and enforce only that domain's configured password/OIDC/OAuth methods. Carry immutable domain identity through login, refresh, project changes, request authorization and client state. Default is a real selectable domain, not an implicit fallback.
6. Add durable per-domain login policy/provider configuration, encrypted provider secrets, exact normalized email-domain allowlists and opt-in email-verified registration policy. Existing Default accounts and projects are preserved; no automatic tenant data migration or role grants.

## Capabilities

### New Capabilities

- Tenant IAM and verified-email onboarding.
- Per-domain login policy and OIDC/OAuth provider administration.
- Domain-first login and domain monitoring.

### Modified Capabilities

- System administrator authorization, session context, project selection and cross-project inventories.
- Existing admin Identity/credentials and request/session observations.

## Impact

FastAPI identity/session/Keystone adapters, SQL policy/onboarding persistence and migrations, Redis session/observation context, Svelte auth/navigation/IAM/admin surfaces, locale catalogs, security-boundary tests and existing architecture/API/deployment documentation are affected. Reuse existing primitives, role graph, SMTP, SQL/Redis and SDK conventions. No production deployment, credential copying, default-user relocation, hidden fallback login, or operational IAM mutation is authorized. Provider federation configuration and SMTP/cloud availability are real prerequisites, never simulated as production success.

Verification separates permanent security regressions, actual local HTTP/SQL/Redis execution, synthetic-provider browser checks and real cloud/provider acceptance. Build/deploy affected declared image architectures through canonical development paths where authorized; preserve other work, data and private inputs. Production mixed-version schema compatibility remains unqualified without an approved production snapshot/revision and restore evidence.
