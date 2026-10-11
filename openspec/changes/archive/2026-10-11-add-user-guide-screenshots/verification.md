# Actual user-guide screenshots — completion evidence

Date: 2026-10-11. Local implementation and browser validation only; not a deployment record.

## Delivered

- 15 public guides, 42 actual-console WebP captures, each 1440×1000; total final asset size 1,387,760 bytes.
- Typed section/step screenshot metadata; shared escaped figure with meaningful alt/caption, intrinsic sizing, lazy loading, safe original-image new-tab action and a 44px minimum hint area.
- Korean, English, Japanese and Simplified Chinese descriptions/actions. Every language explicitly identifies the shared images as Korean-console captures with personal/resource information hidden. Image descriptions participate in existing localized search.
- Real pre-submit, existing-resource, empty, denied and beta-gated states are described honestly. Octavia's captured TCP configuration is distinguished from the HTTP example.
- Four observed visual/usability issues, with route, conditions, impact, safe evidence, recommendation and unresolved status: [`docs/user-guide-visual-review.md`](../../../../docs/user-guide-visual-review.md).
- Maintenance, design, architecture, changelog and the `public-service-docs` main specification updated. Existing unrelated working changes preserved.

## Exercised verification

| Check | Observed result |
|---|---|
| Actual authenticated console | User authenticated directly. Capture navigation used read-only inventory/detail and pre-submit forms; no provisioning, key issuance/revocation, secret reveal, QR/private configuration download or paid model execution. |
| Public guide rendering | Actual local Chromium, 15 guides × 4 languages = 60 routes; 168 figures decoded at 1440×1000 with nonempty alt/caption, localized Korean-console/redaction notice, matching original links and correct document language. |
| Responsive/theme | Lumen guide, 4 languages × 2 themes × 390/767/768/1023/1024/1440px = 48 cases; no document horizontal overflow, bounded figures, unchanged 1.44 aspect ratio and ≥44px hint area. |
| Original-image interaction | Clicked the Octavia listener/pool image action; its separate tab decoded at 1440×1000 and was closed. |
| Final refined project capture | Rendered the final privacy-refined project-menu WebP in `/docs/getting-started`; 1440×1000, caption/original URL correct and no page overflow. Foregrounding the browser tab allowed native lazy image loading; a background-tab automation timeout was not counted as a product defect. |
| Public asset delivery | Final project image returned HTTP 200, `image/webp`; production copies of all 42 captures matched final source assets byte-for-byte by SHA-256. |
| Privacy | Contact sheets and needed full images visually inspected; final OCR produced 8 candidate rectangles, classified as public branding/MCP URLs or form defaults (example CIDR/gateway, public DNS resolvers). Actual dashboard project/resource names and resource IDs/IPs were removed from image pixels. OCR is supplementary, not proof of the absence of all secrets. Raw text was not retained; owned scratch images/OCR script were removed. |
| Targeted existing docs tests | `npm run test:target -- frontend:src/lib/docs/catalog.test.ts frontend:src/lib/docs/locales.test.ts frontend:src/routes/docs/routes.test.ts` — 3 files, 36 tests passed. |
| Translation validation | `npm --prefix frontend run i18n:check` — 0 errors, 0 warnings, 37 namespaces, 9596 source messages. |
| Hardcoded text scan | `npm --prefix frontend run i18n:scan` — 0 hard-coded Korean lines in 989 files. Existing exact-source docs exemption convention maintained, including concurrent MCP wording. |
| Production compilation | `npm --prefix frontend run build` — succeeded with `@sveltejs/adapter-node`. Existing noninteractive-tabindex warnings in `DocCodeBlock.svelte` and `ProjectUsageTable.svelte` remain. |
| Architecture freshness | `check_architecture.py --staged --stamp` then `--staged` passed on an isolated frozen temporary index: 2600 source files, `2f6f4bbe0e0d6f6eed28fa9acaad565ee7a72bc1543c0f418e8c2b6791fb0f30`. Shared index unchanged. This snapshot check does not qualify unrelated concurrent WIP or a future commit index. |
| OpenSpec | Change strict validation passed. `public-service-docs --type spec --strict` passed; only informational long-requirement notices. Added screenshot requirement synchronized to the main spec before archival. |

Visual proof is retained in `evidence/docs-lumen-desktop.webp` (Korean/light/1440px) and `evidence/docs-lumen-mobile.webp` (English/dark/390px).

## Explicit limits

- The full `svelte-check` run observed **18 errors and 2 warnings** at the time of execution: MCP access tests' role-query `exact` option, admin chat quota `creditRateSecondary` prop, and my-resources i18n-key typing. None of those 18 errors was in the screenshot renderer. Do not interpret the successful docs tests/build as a clean global type check; unrelated errors were not re-pinned or hidden.
- Full `npm run test:gate`, backend/deployment verification and real provisioning were not run. No commit, push or deployment was performed.
- GBrain state probe reported `no-cli`, no engine configuration and sync off. No new search-capability claim was written to `CLAUDE.md`.
- Lost asynchronous check notifications were reported to the tool runtime; final test/i18n/build results above came from a completed foreground command, not inferred background status.
- The owned local proof tab/server were closed. The user's authenticated console and unrelated browser/services were preserved.
