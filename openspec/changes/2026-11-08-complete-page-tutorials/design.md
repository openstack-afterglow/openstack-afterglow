# Design: complete-page-tutorials

## Existing pattern (reuse, do not replace)
- Engine: `frontend/src/lib/tutorial/engine.ts` (driver.js). Steps are `TourStep` records in `tours.ts`.
- Step anchors: `data-tour="<tour>-<part>"` on elements. `Button` forwards `dataTour`.
- Step advance: `advanceOn: 'click'` (real click advances), `advanceElement` (a different submit control),
  `readyElement` (wait for loaded content), `cancelElement`, `waitTimeoutMs`.
- Reference implementation: `vm-create` (instance create wizard) and `volume` (create dialog → list).
- Persistence: `tutorial_status.py` TOUR_IDS (must match frontend), `POST /api/v1/tutorials/{tour}/status`.
- Strings: `i18n/ns/tutorial.ts` loads `messages/*/tutorial.json`. Every key exists in all nine locales
  (`bn en ja ko ms nb sw vi zh-CN`).

## Split for parallel work (one owner per file)
To avoid collisions, each area owns its own files:
- `lib/tutorial/steps/<area>.ts` exports `<area>Steps()` builders (type-only import of `TourStep` from `../tours`). `tours.ts` only registers them.
- `lib/mockup/<area>.ts` exports a handler `mock<Area>(method, pathname, body)` that returns `undefined` for paths it does not own. Implemented first for storage as `lib/mockup/objectStorage.ts`, following `computePools.ts`. State lives in `state.ts` so tests can reset it.
- `lib/tutorial/tours.ts`, `lib/mockup/transport.ts` dispatch lines, `lib/mockup/contracts.ts` (ADMIN_ALLOWED_PATHS),
  `tutorial_status.py` and the nine locale JSON files are owned by the orchestrator. Workers send key/value fragments.

Areas:
1. storage: file storage, object storage buckets, volumes (detail, backups, snapshots)
2. network: floating IPs, load balancers, networks, routers, security groups, Waygate
3. compute and containers: instances (detail, keypairs, images), containers (clusters, instances), Drover, database
4. identity and chat: IAM users/projects/groups, account pages, chat projects/agents/tools, secrets, Lumen
5. admin: all `/admin/*` routes (projects, credentials, chat providers/models/quotas, quotas, roles, etc.)

## Inventory
Each area's first step writes `openspec/changes/2026-11-08-complete-page-tutorials/inventory/<area>.md` with, per route:
CREATE control, DELETE control, OTHER mutations, existing `data-tour` anchors, `TutorialStartButton` mount, gates
(permission, beta flag, prerequisite resource). The inventory is the source for the tasks list. It is not kept
only in agent memory.

## Verification levels
- Mockup (default for every tour): managed Chromium, `?tutorial=on` or `?tutorial=admin`, walk all steps, assert
  DOM and recorded mock mutation sequence.
- Real session (final): one create and one delete per tour against the local stack. Requires the Chrome relay
  extension to be connected (`browser.targets({app:{relay:true}})`). Until then this level stays unchecked.

## Anchor conventions (learned from the bucket and container pilots)
- `ResponsiveTable` mounts only one of its `cards()` or table snippet per viewport (1024px breakpoint). Anchor the same
  control in BOTH snippets, or a tour fails on one width. Bucket pilot failed at 390px until the card button was anchored.
- Every delete step MUST anchor only to the item the tour just created. Record that item's identity on the page (name, or
  uuid/id from the create response), pass it as a highlight prop, and put the conditional `data-tour` on the matching
  row's delete control in both snippets. Never anchor a generic delete control: real lists are not empty, so a generic
  anchor can make the tour delete a pre-existing resource. Step `readyElement` must wait for that specific anchor.
- A final step must point at a section that still renders after the delete. A list wrapper inside `{#if items.length > 0}`
  unmounts when the last item is removed; anchor the trash/result section instead, and verify its text in the browser.
- Anchor `confirm-accept` (global ConfirmDialog) for delete confirmations; do not add per-page confirm anchors.
- All web control and verification uses the `agent-browser` CLI (vercel-labs/agent-browser, 0.41+). Get a stable session name with `agent-browser session id --scope worktree --prefix task` and pass `--session <name>` on every command. Use `snapshot -i` refs for clicks, `wait` on the expected element or text after each action, and `agent-browser set viewport 390 844` for mobile. Do not use the omp `browser` tool for these walks.
- Admin-profile mock dispatch must sit ABOVE the `profile === 'admin' && method !== 'GET'` guard in transport.ts, or admin POST/DELETE hit `mockUnsupported` first (announcements pilot hit this).
- `engine.test` accepts only plain `[data-tour="…"]` step selectors. No `:has()` or compound selectors; give the form or frame its own anchor.
- A custom delete dialog needs its own confirm anchor. `confirm-accept` covers only the global ConfirmDialog (IAM projects uses its own).
- Browser walks for batch verification run against a frozen snapshot (`vite build` + `vite preview` on a dedicated port), not the shared HMR dev server. Peer edits trigger full reloads that reset the in-memory mock and produce false failures.

## Non-goals and rules
- No new tour engine. No change to backend resource APIs.
- A tour step must never click a control that is absent in mockup or gated off for the user; gate with `skipIf`.
- Delete steps must confirm via the page's real confirm dialog and use a sample resource created inside the tour.

## Viewport policy (decided 2026-11-08)
Tutorials are provided only at tablet width and above (`md`, >=768px, DESIGN.md breakpoints). Mobile (<768px) has no tutorial by design: pages with many controls leave no room for the popover. `TutorialStartButton` does not render below 768px and `startTour` returns false there (also blocking saved-tour resume and `?tour=` links). Acceptance walks run at 768x1024 and 1440x1000; 390px walks are no longer required, and earlier 390px failures are recorded as history only. `ResponsiveTable` still mounts cards below 1024px, so card-snippet anchors stay required for the 768-1023px range.

## Read-only pages (no tutorial)
Pages with no create or delete flow get no tutorial and are recorded here so the batch does not revisit them. Overview, monitoring tree, events, topology, system info, dashboard home, and usage pages are read-only. Settings pages that only change preferences (no resource create/delete) are also excluded. A page moves off this list only if it gains a create or delete action.
