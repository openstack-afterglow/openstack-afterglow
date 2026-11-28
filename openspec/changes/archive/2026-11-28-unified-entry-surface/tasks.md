# Tasks: unified-entry-surface

Base: dev 6cb3a871.

- [x] Add `EntryTopbar`, `EntryStage`, `entryNav` and `--entry-nav-height`.
- [x] Landing, AuthStudioShell and ConsoleEntryTransition render the shared bar and stage; remove the auth footer row.
- [x] Auth card layout below 1024px; split layout from 1024px.
- [x] Rewrite route-scene CSS: `--stage-vt-*` part names, still bar, overlay bar names, panel offset below 1024px.
- [x] Update designSystemRules contract (shared bar/stage on the three surfaces).
- [x] DESIGN.md, ARCHITECTURE.md, CHANGELOG.
- [x] Visual verification in Chromium (vite dev, mocked auth API, scene slowed to 2880ms): desktop 1440×900 and mobile 390×844 for landing→login, login→landing, password login→console; every transition finished, no page errors.
- [ ] NOT RUN locally: contract/functional gates that need Docker services (CI covers). SSO callback not verified against a real provider.
