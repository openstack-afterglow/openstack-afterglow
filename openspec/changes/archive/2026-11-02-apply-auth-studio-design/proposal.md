## Why
The user approved the themed viewport-fit login/logout studies in `output/afterglow-login` and asked to apply them to the real `/login` and `/logout` routes.

## What Changes
- New shared `AuthStudioShell` (brand/locale/theme topbar, `AfterglowOrbit` identity art with pause control, form panel, footer) using app design tokens.
- `LoginPage` adopts the studio form styling with a password visibility toggle; all credential, SSO, recovery, signup, IME and session-fence logic is unchanged.
- `/logout` adopts the studio panel; cleanup steps, status/error copy and leave gating are unchanged.
- New `authStudio.*` copy in all nine locales.
