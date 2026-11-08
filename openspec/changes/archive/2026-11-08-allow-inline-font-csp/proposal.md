## Why

KaTeX bundled CSS inlines small WOFF2 font files as `data:` URIs during Markdown math rendering in chat messages. The previous frontend Content Security Policy restricted `font-src` to `'self' https://fonts.gstatic.com`, causing the browser to block inline math fonts with a CSP violation warning.

## What Changes

- Update `font-src` in `frontend/src/hooks.server.ts` to include `data:`.
- Add regression coverage in `frontend/src/hooks.server.test.ts` verifying that `data:` URIs are permitted for fonts without loosening other directives.
- Document the font CSP policy in `docs/security.md`.

## Capabilities

### New Capabilities
- `frontend-content-security-policy`: Governs browser-enforced Content Security Policy directives emitted by SvelteKit server hooks, specifically font asset loading permissions.

### Modified Capabilities
<!-- None -->

## Impact

- Frontend SvelteKit server hooks only (`frontend/src/hooks.server.ts`).
- No backend API or database schema changes.
- Safe for browser rendering: font assets cannot execute arbitrary script.
