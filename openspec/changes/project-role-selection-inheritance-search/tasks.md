## Implementation Tasks

- [x] Inspect current modal/types and verify assignable_roles preserves real trusted inference metadata.
- [x] Implement transitive parent-selected descendant state, separate externally inherited state, protected-role restrictions and direct-only saving without destructive normalization.
- [x] Add localized searchable role name/ID/description filtering and accessible empty-result feedback while retaining hidden selections.
- [x] Regress parent add/remove, transitive/shared descendants, original explicit children, external inheritance, nonowner/busy protection and search/save transitions in final behavioral tests.
- [x] Initial integrated architecture/design/detailed contracts and project gate backend4,284/frontend2,523+runner9/contracts154/functional35 and Ruff pass, before the subsequently identified external-overlap correction.
- [x] Actual server role-ID catalog and unchanged local Keystone session: Lumen parent selects15 checked/disabled descendants, removal re-enables, search returns16 Lumen roles, empty feedback and hidden explicit leaf retention pass. Modal containment/overflow0 at390/767/768/1023/1024/1440px; cancel-only/no grant mutation, actual light/dark screenshots. Native SDK authorization/runtime proof is separate.
- [x] Reproduce overlapping group/domain inheritance failures before correction (HTTP external metadata absent; modal loses inherited child), independently expand existing external assignment rows, migrate all member DTO fixtures and confirm membership50/frontend23 changed-surface regressions.
- [ ] Qualify corrected final source with typecheck, current-source rebuilt backend/frontend HTTP/browser overlap smoke, full project gate and staged architecture guard; record distinct synthetic fixture and real unchanged identity evidence before archive.

Production Lumen403 evidence is tracked separately in fix-local-service-authority-debug; never conflate graph UI proof with native service authorization proof.

## Actual browser evidence

- Private credential-free `role-editor-final1310.json` and screenshots record current-source local runtime. The native headless browser additionally selected `lumen-inventory_reader`, hid it with WAYGATE search, restored LUMEN search and observed its retained selection, then cancelled without saving.
- The initial `npm run test:gate` qualified the initial integrated feature source. Final qualification must include the later independent external-role projection; versioned immutable publication and production acceptance belong to the parent release, not this local UI checklist.

