# Explicit cross-domain administrator group members

## Why
Administrator groups currently search only home/joined users from the selected group domain. Human identities are being consolidated in Accounts, so a system administrator must explicitly select another identity home and find/add its users without changing the group domain or requiring a preexisting organization grant.

## What Changes
- Keep the existing group-domain home/joined candidate directory as the default. Add an explicit account-home-domain selector in the expanded group member search; no global/all-domain option or workspace change.
- Use a system-admin-only exact-group candidate endpoint for an explicitly selected source home domain. Preserve names, email, full native UUID and home-domain IDs; exact enabled source/user/group boundaries, truthful loading/error/retry and no stale cross-source publication.
- Explicit cross-home membership PUT carries `user_domain_id`. Under the existing graph lease, freshly authorize the system administrator and verify exact enabled user/home and target group/domain. This explicit group admission may establish membership and grant the group's roles in the group's own domain. Existing membership proof remains mandatory for group grants affecting other domains; owner-bearing, projection, last-manager/system-admin, provider, mutation ambiguity and invalidation fences remain.
- Generic default membership and all organization-manager/credential/project/role APIs remain unchanged. No account migration, automatic extra role grants, service/config/schema changes, shared/production deployment or native IAM mutations during verification.

## Verification and preservation
Focused backend and component/controller behavior regressions for an Accounts user not already joined; same-name email/UUID selection; disabled/mismatched source; source ABA and pending/error/retry; default-only behavior and strict manager/owner protections. Exercise real Uvicorn/installed SDK over isolated synthetic native TCP and the actual compiled page across nine locales, themes and responsive breakpoints. Run the related Access target and final isolated canonical gate. Keep shared dev index/review marker, concurrent work, private inputs, running services and cloud resources intact. Evidence is source-only and separates synthetic provider boundaries from live acceptance.
