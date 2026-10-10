## Why

The live Grafana Node Exporter kiosk footer moves upward over charts when its iframe width crosses 543/544px. The footer is inside Grafana, not Afterglow; wide-layout parent height is capped to the viewport while dashboard content overflows it. Cross-origin Afterglow CSS cannot repair its sticky containing block.

## What Changes

Add Grafana's supported `hideLogo=1` query parameter to shared dashboard and solo-panel embed URLs. This suppresses the kiosk branding footer without modifying iframe sizing, auth, CSP, dashboard variables, range, panel identifiers, Grafana deployment settings or upstream CSS. Use `1` because upstream `shouldHideDashboardKioskFooter` explicitly accepts that string.

## Acceptance

- Dashboard and solo URLs contain exactly one enabled hideLogo flag and retain existing query semantics.
- Actual Grafana dashboards still render and scroll at portrait, wide-layout boundary, tablet, desktop and short landscape sizes with no branding footer.
- Verify the changed Svelte component inside the actual Afterglow browser surface using synthetic identity/context only; Grafana content must remain live.
- Preserve unrelated development changes. No commit, push, production configuration mutation or deployment is requested.
