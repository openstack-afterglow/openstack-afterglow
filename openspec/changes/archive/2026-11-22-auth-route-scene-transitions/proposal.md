# OpenSpec Proposal: auth-route-scene-transitions

## Why
Entering the console is three visually unrelated screens: the full-screen landing hero, the split
`AuthStudioShell` login, and the console. Each step cuts hard even though the landing hero and the auth
identity panel already render the same `AfterglowOrbit` scene. The user asked for motion-graphic transitions:
landing → login (artwork making room for a login panel that arrives from the right), and login (password or
SSO callback) → loading → console.

## What Changes
1. **Landing ↔ login route scene** (`lib/utils/routeScene.ts`, root `+layout.svelte` `onNavigate`):
   a same-document View Transition only for `/` → `/login` (`auth-enter`) and `/login` → `/` (`auth-leave`).
   The landing hero and the auth identity share `view-transition-name: afterglow-art`, so the full-screen
   artwork morphs into the identity side; the auth panel slides in from the inline end (reverse on leave).
   Names exist only while `html[data-route-scene]` is set. Skipped when the hero is off screen, under reduced
   motion, or without `document.startViewTransition` (plain navigation).
2. **Console entry scene** (`lib/stores/consoleEntry.ts`, `components/auth/ConsoleEntryTransition.svelte`):
   after a successful password login or SSO callback publishes the session, an overlay above the routes
   grows the auth artwork across the screen while the panel leaves, shows real state copy (session verified,
   opening workspace) on the orbit, and reveals the console once the real navigation settles and the entrance
   motion has finished. No fake progress, percent or minimum wait; failure or a cancelled navigation reveals
   the page it landed on.
3. **Motion token** `--motion-duration-scene: 720ms` (layout.css, reduced-motion block, `MOTION_CSS_VAR`,
   `MOTION_DURATION_MS`, designSystemRules test, DESIGN.md Motion).
4. Copy `consoleEntry.*` in `public-entry` for all nine locales; ARCHITECTURE.md and DESIGN.md updates.

## Out of Scope
- Logout, signup, recovery and consent surfaces keep their current behavior.
- No polyfill for browsers without View Transitions.
