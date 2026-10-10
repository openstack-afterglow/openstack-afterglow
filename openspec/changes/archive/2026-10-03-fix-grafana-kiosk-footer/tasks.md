## Tasks

- [x] Verify official hideLogo option and accepted values on live Grafana.
- [x] Update shared GrafanaEmbed dashboard/solo URLs and exercise regression coverage.
- [x] Verify the actual Afterglow iframe with live Grafana at responsive sizes and during scrolling.
- [x] Update architecture, monitoring documentation and changelog; record verification and archive.

## Verification

- Upstream DashboardScenePage passes hideLogo to shouldHideDashboardKioskFooter; the helper explicitly accepts string `1`. Live `/d/afterglow-node` with `hideLogo=1` rendered 23 panels and zero public-dashboard-footer nodes. Original footer drift reproduced in the preceding investigation; no repeated root-cause investigation or Grafana CSS modification required.
- Dashboard/solo regression: both failed before the change (expected hideLogo `1`, received no flag), both passed afterward. Related context-store/observability checks: 3 files, 12 tests passed. Svelte check: 2,131 files, zero errors/warnings.
- Full frontend: 277 files, 1,898 tests passed; file-log runner 9 passed. Production adapter-node build passed. Full project `npm run test:gate` was not run; no commit or push performed. Backend is unchanged.
- Actual SvelteKit `/admin/monitoring/node` compiled from modified shared source: 427×874, 767×900, 768×1037, 1023×900, 1024×900, 1027×510, 1440×900; each frame scrolled 0/150/300px. All retained 23 panel headers, zero footer nodes, zero app horizontal overflow. The real `/d-solo/afterglow-node?panelId=1` rendered its live host-count panel with no footer.
- Identity/Grafana context API only were synthetic; embedded Grafana and metric panels were live. An isolated temporary public config allowed exactly the configured Grafana origin through the existing CSP builder; no CSP override, auth bypass, production config change, shared service restart or deployment.
- Scoped architecture review used a copied guard/document and temporary index over HEAD plus owned source/docs: `29ca780ec96b6e8b1b3cc09421677c0ae5bacf5a2ea8dcfc8f22b2598823a149`, 2,165 files; `--staged --stamp` and `--staged` passed. Real index SHA-256 remained `aaad3848502699e76bad1f016c180ec7bd193c57bec17bc4538bc50f5d9ac5b9`; shared review block preserved. Committer must stamp the actual eventual staged scope, including other sessions' work, before the project gate/commit.
