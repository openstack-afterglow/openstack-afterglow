# App slop cleanup (login, dashboard, Lumen chat)

## Why
The Impeccable overlay flagged the login/logout shell (tracked eyebrows, decorative `: : CLOUD WORKSPACE : :`, crushed headline tracking), dashboard stat tiles (cyan/violet/blue per-tile palette), the sidebar project label and chat text below legible sizes, and the chat empty state (icon tile above heading).

## What changes
- Remove the eyebrow kickers and the decorative index from the auth shell, login and logout pages, with their locale keys.
- Raise heading tracking to -0.03em (auth) / -0.035em (landing headings) / -0.04em (hero wordmark).
- Dashboard stat tiles use a new neutral tone instead of per-tile blue/cyan/violet.
- Remove the icon tile above the Lumen empty-state heading.
- Raise chat functional text to an 11px floor and the disclaimer to 12px; the left-rail project label to 12px without uppercase tracking.
- The SSO callback pending view shows its message once (heading) and keeps one accessible status; the progress bar aligns with the heading.

## Non-goals
No API, auth, permission, data or copy changes beyond the removed decorative labels. Table cell padding is unchanged: a local render of `RecentInstancesCard` at dashboard width measured text 15px or more from every table boundary, so the overlay's "cramped padding" note was not reproduced and a global `TableShell` change was reverted. The overlay's "monotonous spacing" note on the callback screen is not addressed.
