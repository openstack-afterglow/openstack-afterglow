## Why

The published i18n branch localized the older dev base 0f59e0ee, while current GitHub dev has added navigation, landing, model/media pricing, host capacity, security-group union and Palimpsest package surfaces. The user requires each localization update to incorporate latest dev first. Fetch on this run selected `ff007edb6e4bf75f0c0a05107ca6340b593675ff`; an ordinary merge is in progress with 28 conflicted files. The pre-existing workflow rule was preserved in commit a6c01409.

## What Changes

- Complete the ordinary dev merge without rewriting published i18n history, preserving latest application behavior, authorization, identifiers, payloads and UI structure.
- Reconcile navigation/chrome, landing, chat media/model/SDK guides, VM capacity and security-group refresh/union conflicts while retaining locale persistence, SSR and reactive translations.
- Localize newly introduced/changed visible Korean and English text using existing ko/en/ja/zh-CN feature namespaces, safe rich messages and call-time formatting; keep translations explicitly draft.
- Cover new Palimpsest package and ProxySQL monitoring UI and any additional scanner findings. Update contribution workflow guides to require latest-dev synchronization.
- Verify catalog parity/arguments, hard-coded guard, Svelte diagnostics, production build, full project gate and actual browser surfaces. Fetch again before delivery and record the incorporated dev SHA.

## Capabilities

### New Capabilities

None: existing localization is extended to current application surfaces.

### Modified Capabilities

Frontend four-locale coverage now tracks the latest dev application instead of the original localization branch point.

## Impact

Only the dedicated `/Users/pieroot/code/afterglow-i18n` worktree is edited. Integration imports upstream backend/config/dependency changes unchanged; localization changes remain frontend/docs only. No real login, provider inference, OpenStack mutation, deployment, PR or force push. Merge completion requires fresh verification and architecture review; unsaved page forms can still reset on locale change, and target translations still require native review.
