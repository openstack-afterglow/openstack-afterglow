## Why
The administrator Identity user list has no account deletion action. Operators need explicit removal of unwanted real native users; an unknown display name is not proof an account is safe to delete.

## What Changes
- Add fresh-system-admin DELETE /api/v1/admin/users/{user_id}?domain_id=exact-home with domain verification and existing graph lease, ownership/journal/last-admin/last-domain-manager/session invalidation guards.
- Protect actor self and configured/native service identities. Native user deletion never deletes projects or cloud resources and never silently succeeds for missing users.
- Add visible desktop/card user-delete action with exact identity/domain confirmation and typed full user ID; no automatic retry after uncertain mutation, no stale actor/domain/ABA submission.
- Preserve existing auth, scopes and unrelated shared WIP. No orphan native-grant cleanup or blanket 404 tolerance in this change.

## Acceptance
- Ordinary selected-domain native user deletion works; nonadmin, wrong-domain, self/service, ownership and last-authority cases cannot mutate.
- Successful deletion revokes active sessions and invalidates authority/inventory; native failure is visible.
- Frontend cancellation, typed-ID mismatch, scope/session change and errors cause no unintended/replayed delete. Mobile/tablet/desktop retain accessible action and confirmation.
- Source regressions plus isolated API and browser smoke; no operational user deletion/deploy.
