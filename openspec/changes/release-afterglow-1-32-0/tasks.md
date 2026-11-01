## 1. Prepare

- [x] 1.1 Inspect current source, branch, releases and requested GitHub-only scope.
- [x] 1.2 Review all pending implementation and synchronize minor1.32.0 metadata and notes.

## 2. Verify and publish

- [x] 2.1 Full repository gate, frontend check/build and changed-path runtime smoke (backend12375/frontend6422/contracts183/functional167; compiledresizePOST1/refresh503 retained; authHTTP503×3 local-onlylogout).
- [ ] 2.2 Commit current reviewed changes and push dev without main merge or history rewriting.
- [ ] 2.3 Wait exact-SHA CI, create immutable tag and publish GitHub release notes.
- [ ] 2.4 Verify tag image/Helm jobs, release revisions/digests/latest, archive publication change and record production hold.
