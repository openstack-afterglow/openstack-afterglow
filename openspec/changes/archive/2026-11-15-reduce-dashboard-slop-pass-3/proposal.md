# Reduce dashboard slop — third pass

## Goal and boundaries

Audit the remaining consumer, administrator and public-entry surfaces on integration/20261116-tutorial-slop (2efce387), using a new ux/slop-pass-3 worktree only. Preserve the incumbent DESIGN.md identity, copy, resources, permissions and tutorial availability semantics. No integration into shared dev, publication, deployment or production writes.

Parent subsequently authorized importing the existing local dev 2d7c823b (1.32.20) without fetch/push to obtain its already-fixed tutorial expectation (36285613). The branch fast-forwarded with owned changes preserved; architecture/testing documentation conflicts were resolved without manually editing tutorial semantics or tests.

## Evidence-led scope

Use the existing local tutorial transport and real locally served public pages. Scan rendered DOM with Impeccable at 390×844, 768×900 and 1440×900, both themes, Korean/English/Japanese. Exercise safe native accessibility interactions, open panels/dialogs/menus, capture paired screenshots and a recording. Record exact effective routes and unavailable fixtures; never infer hidden acceptance from redirects.

The first 282 consumer cases expose shared neutral-chip contrast below 4.5:1, legacy light state text contrast, incorrectly colored warm button text, repeated table/card nesting in detail views, account heading skips and nested alerts, Lumen settings kickers/disabled ink and tools placeholders. The remaining administrator/public audits are independent read-only slices. Fix verified defects at their shared cause or narrow composition owner, not detector false positives. Existing character art and status glyphs are authored identity. Motion, chart disclosures and mobile refresh require concrete usability evidence before changing.

## Acceptance

Resolve real measured defects without new palettes, motion, dependencies or authority. Preserve accessible actions and complete data at all widths. Measure computed contrast for color fixes; inspect before/after native interaction and recordings. Re-scan changed surfaces and document every accepted exception and unavailable state. Run canonical isolated detached-worktree test:gate, architecture stamp/guard, staged guard and diff whitespace check. Update CHANGELOG, DESIGN, testing evidence, archive this package and commit on ux/slop-pass-3.

Pre-hover canonical source 96e8dcf3b97edd5d80dc1055f41b46ed88bc3d8623a34028a1e1016f5c9b0ea5 (4348 files) passed the complete isolated gate: backend 15221 passed/106 skipped, frontend 592 files/8014 tests, contracts 262 passed, functional 292 passed/46 skipped/131 deselected, Ruff 912 files. Earlier failures and pristine-dev classification of the ownership-heading selector remain documented. The matched 180-case consumer comparison reduced raw findings 446→48; all contrast, nesting, heading-skip and kicker findings in that comparison were removed. Remaining detector results are explicitly classified, not hidden or advertised as global WCAG conformance.

The bounded final state check then found light warm-fill hover at 4.03:1 despite its 4.94:1 resting contrast. The existing light hover token now mixes toward base surface instead of dark ink; dark behavior stays unchanged. Acceptance requires both states and the complete gate on this final source rather than borrowing the earlier green result.

Final hover-qualified source 64f0c73dcc36e01db923f7ffcd7b7b6facd498882624d0791e9ef58680fb14a0 passed the complete isolated gate in 299.95s with the same lane counts. The three named warm controls pass all 12 rest/hover/theme scans: light 4.94/5.87:1, dark 7.95/8.73:1. Administrator evidence covers 288 route cases and 270 interactive/supplement captures. The sparse selected-user overview's equal-height grid remains an explicit P2 layout limit; changing its directory/aside ownership is outside the bounded border/contrast refinement.


## Limits

All authenticated evidence is synthetic tutorial data with an unused loopback API base. Public pages use actual source but unavailable backend/auth operations remain unavailable. No live authentication, native service, cloud workload or production readiness is claimed.

Volume and Magnum detail fixtures expose their unsupported-operation error state, not their full native detail path. File-network/security/snapshot routes retain the beta gate. Container inventory includes a verified synthetic empty list; Lumen chat lacks its real model/conversation backend. A valid transfer lookup/receipt and authenticated command palette were not fabricated.
