## 1. Implementation
- [x] 1.1 Correct Waygate member Trust token scope without weakening grant lifetime and role ceiling.
- [x] 1.2 Move admin version information to System > System information.
- [x] 1.3 Correct Drover initial progress bar and stage estimates.
- [x] 1.4 Verify quota before Drover native writes; retain provider race/unknown fences.
- [x] 1.5 Increase source fallback personal-project security-group and rule limits; retain saved policy and existing projects.
- [x] 1.6 Keep active Drover operation status in a scoped, minimizable, non-dismissable background dock.

## 2. Verification and documentation
- [x] 2.1 Exercise actual native SDK/HTTP scenarios and targeted contract tests.
- [x] 2.2 Verify rendered responsive UI and its real operation tracker lifecycle with isolated synthetic fixtures.
- [ ] 2.3 Update architecture, docs, changelog and exact source verification; archive once complete.

Full Afterglow gate and shared whole-tree architecture stamp are not claimed: the shared checkout includes concurrent unrelated changes. Waygate and Drover existing shared dev trees are respectively behind origin/dev and carry unrelated user WIP; release-compatible Waygate patch is kept separately at `/tmp/waygate-scope-0.3.6-20261104.patch`. No production deployment or live cluster retry was performed.
