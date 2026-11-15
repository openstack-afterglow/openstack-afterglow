# Reduce dashboard visual slop (overview surface and shared tokens)

## Goal

Remove four measured design defects from the project overview and the shared primitives it uses, without changing data, permissions, copy or layout structure.

## Evidence (same environment before and after)

Baseline and after both come from a local build of dev `bf81601f` in tutorial mode (`/dashboard?tutorial=on`), scanned with `impeccable detect --cdp` at 1440x900 and 390x844 and driven with `agent-desktop`. The earlier production scan (1.32.15, live data) is only evidence of the live state and is not the comparison baseline because rendered counts move with data.

| Scan | Desktop | Mobile |
|---|---|---|
| Local before | 4 (low-contrast, nested-cards x2, bounce-easing) | 11 (low-contrast, nested-cards x8, bounce-easing; 6 card-in-card tables/cards plus 2 compact cards and 1 alert) |
| Local after | 0 | 0 |
| Production 1.32.15 (reference only) | 2 | 5 |

## Changes

- `RangeToggle`: unselected 24h/7d/14d text uses `--color-ink-2` instead of `--color-ink-3` (light 4.1:1 on the sunken track to 5.92:1; dark 5.58:1).
- `ResponsiveTable` gains `embedded`: inside a `Card` the table shell and compact resource cards become hairline-divided rows instead of a second bordered box. Used by the recent-instances card and the chart data tables (`BklitChart`). The recent-instances table also gets a 0.75rem gap below the regex-search hint.
- `Alert` gains `flat`: tone-coloured text without a second box. Used for the reminders card list and load error, separated by dividers.
- The overshoot easing is removed (`--motion-ease-overshoot`, `MOTION_CSS_VAR.easeOvershoot`, `MOTION_EASING.overshoot`, JS `pop()` back-out). `.motion-pop` and `pop()` use the single decelerating `--motion-ease-emphasized` curve. DESIGN.md and the design-rules test are updated and a new guard rejects any cubic-bezier control point outside 0..1.

## Non-goals

No production deployment, no data/permission/copy changes, no change to the character-interface status chips (an authored part of the design system), no global `--color-ink-3` change, and no layout redesign. Remaining observations (two stacked disclosures per chart card, icon-only refresh on mobile, repeated entrance on 49 files) are listed as follow-ups, not changed here.
