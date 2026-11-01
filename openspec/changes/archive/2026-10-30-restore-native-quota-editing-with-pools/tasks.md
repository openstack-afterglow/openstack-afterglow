## 1. Native authority

- [x] 1.1 Confirm stale writer/default/UI coupling and define independent native quota contract.
- [x] 1.2 Restore cores/RAM allocation budgets, project quota edits and future defaults for active/paused pool domains without weakening native guards.
- [x] 1.3 Cover GPU-only pool native quota adjustment→eligibility, paused edits, defaults and budget denial.

## 2. Interface

- [x] 2.1 Remove obsolete pool gating props/state from native quota editors and every caller, preserving native snapshot/authority guards.
- [x] 2.2 Verify manager/admin CPU/RAM controls submit explicit native quota/default edits independently of pool status.

## 3. Verification

- [x] 3.1 Run affected regressions and real installed-SDK HTTP+browser smoke, then affected image execution. Before nativePUT409 with CPU/RAM blockers; after200 and fresh GPU eligibility true, disabled-project defaults readback, pool metadata unchanged; browser native edits/defaults/admin ceilings with independent pool503;54locale/theme/width conditions and6dualarch builds/runtimes.
- [x] 3.2 Run canonical gate and record remaining unrelated lint/format failures without claiming green. Focused341backend/122frontend pass; canonical backend11397pass/106skip, frontend5928pass, contracts183pass, actualdatastore167pass/37deselected. Gate ends at untouched main.py I001, not green.
- [x] 3.3 Update architecture/API/operator/testing/changelog, sync specs and archive.
