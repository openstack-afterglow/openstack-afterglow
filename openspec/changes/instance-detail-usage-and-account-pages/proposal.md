# Instance detail usage period and account page clean-up

## Why

Owner review (2026-11-16) of the instance detail and account settings pages:

- The usage period was a separate full section. The expiry belongs next to the creation date, and changing it is an action like start/stop.
- 「파일 스토리지 접근 권한」 and 「Afterglow 정보」 (union strategy/libraries) on the instance detail are no longer how those features are managed.
- Login workspace reconnect was opt-in; the owner wants the last accessed domain+project by default and a manual fixed default when the user turns it off.
- Users want one SSH keypair applied automatically when creating an instance.
- Session rows show only OS/device; users cannot tell which browser a session belongs to or where its IP is.
- The account activity page lists request telemetry (`request.read`, `request.stage`) that ordinary users do not need.
- The domain+project selector is slow to list and to switch.

## What Changes

1. Instance detail: expiry date and expiry action under the creation date; a 「기간 연장」 button in the header action row opens the existing usage editor in a dialog; `#usage-schedule` reminder links open that dialog; a failed usage read shows an error with retry in the panel. The file-storage access and Afterglow information sections are removed from the UI (backend APIs unchanged).
2. Login workspace: absent preference reconnects to the last accessed domain+project; opting out requires choosing a fixed domain+project, validated server-side, never overwritten by later switches.
3. Default SSH key: per-user default keypair, chosen on the SSH key page and preselected by the instance wizard.
4. Sessions: browser name and major version from the User-Agent, and the IP country from the deployment GeoIP database when available.
5. Account activity: the user endpoint returns only intentional resource changes and security-relevant account actions; administrator views are unchanged.
6. Workspace selector: analysis of native calls per action and safe parallelization without removing authorization checks.

## Capabilities

### Modified Capabilities

- `console-workspaces` (login workspace default, selector latency)

Other items are UI/preference behavior recorded in `ARCHITECTURE.md`, `docs/testing.md` and `CHANGELOG.md`.

## Impact

Frontend instance detail, account settings sections, VM wizard keypair step, i18n (nine locales). Backend: login preference service and profile API, a keypair default preference endpoint, session metadata and listing, user activity query, workspace switching services. No schema migration.
