## 1. Prepare

- [x] 1.1 Inspect current source, branch, releases and requested GitHub-only scope.
- [x] 1.2 Review all pending implementation and synchronize minor1.32.0 metadata and notes.

## 2. Verify and publish

- [x] 2.1 Full repository gate, frontend check/build and changed-path runtime smoke (backend12375/frontend6422/contracts183/functional167; compiledresizePOST1/refresh503 retained; authHTTP503×3 local-onlylogout).
- [x] 2.2 Commit all77reviewed files as `a8e993911f9793ef0b6b73aad0dba9a1f5adcbe2`, pushdev; no main merge/history rewrite.
- [x] 2.3 Exact-SHA devCI41332584500success, immutablev1.32.0 and GitHub release notes published.
- [x] 2.4 TagimageCI41333266068/Helm41333266023success; API/frontend/workerrelease/latest indexdigest+revision verified, published amd64image3 network-none smokes passed. Archive publication change; controller1/native/schema/shared-writer/cold-backup hold remains and production mutation0.
