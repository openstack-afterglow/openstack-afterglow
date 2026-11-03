## Release

- [x] Freeze current public changes; preserve shared index and private state.
- [x] Review backend and frontend; fix catalog-token and cancellation regressions.
- [ ] Verify whole gate, actual runtime and production images.
- [ ] Commit and push exact candidate; wait for exact-SHA CI.
- [ ] Publish immutable 1.32.4 tag, Release, images and Helm; verify identities.
- [ ] Record evidence, archive and clean owned isolation.

## Production

Do not start new writers or migrate until actual SQL105, original key, native services, writer fencing and recovery prerequisites are qualified.
