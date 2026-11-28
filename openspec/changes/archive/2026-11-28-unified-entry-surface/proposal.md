# OpenSpec Proposal: unified-entry-surface

## Why
User review of the entry scenes (2026-11-28): landing → login and login → console now read as one motion,
but the screens themselves are different designs (landing nav vs auth topbar and footer row, landing hero
caption vs auth identity copy, overlay status on the orbit), so the scene only morphs between similar areas.
The user asked for one identical design where only the width changes, and to change the whole design so
that is possible.

## What Changes
1. **One bar** `lib/components/entry/EntryTopbar.svelte` (+ `entryNav.ts`): landing, every `AuthStudioShell`
   surface and the console entry overlay render the same fixed bar (brand, landing section links, actions)
   at `--entry-nav-height`. Links stay centered whatever the actions hold. The landing gains `ThemeSelect`;
   auth surfaces drop the console action; the overlay copy is inert and has no actions.
2. **One stage** `lib/components/entry/EntryStage.svelte`: AfterglowOrbit, signature + motion control,
   wordmark + one-line lead + fixed-height action row, footer line. The landing hero, the auth identity side
   and the overlay are this stage. The auth footer row is removed (its text moves under the panel's support
   code); auth identity copy becomes the stage lead (`authStudio.*.headline1/2`).
3. **Layouts**: auth splits stage/panel from 1024px; below 1024px the stage is the full background with the
   centered card (previously only below 768px).
4. **Scenes** (`routes/layout.css`): stage parts get view-transition names through `--stage-vt-*` while a
   scene runs, so each part travels with its edge or the centre; the bar holds still and only differing
   actions cross-fade; the console overlay keeps the bar and widens the stage under it. `scene-copy-*` and
   `console-entry-copy` names are removed.

## Out of Scope
- No API, store, session or routing change. No new token besides `--entry-nav-height` (layout value).
- No production deployment or tag.
