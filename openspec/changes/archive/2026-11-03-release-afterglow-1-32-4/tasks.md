## Release

- [x] Freeze current public changes; preserve shared index and private state.
- [x] Review backend and frontend; fix catalog-token and cancellation regressions.
- [x] Verify whole gate, actual runtime and production images.
- [x] Commit and push exact candidate; wait for exact-SHA CI.
- [x] Publish immutable 1.32.4 tag, Release, images and Helm; verify identities.
- [x] Record release evidence and archive the release checklist.

## Production

Do not start new writers or migrate until actual SQL105, original key, native services, writer fencing and recovery prerequisites are qualified.

## Publication evidence

- Source `1b495807d31037732d248e598396eb293d0393a5`; exact-SHA CI 41592545469, tag images 41593479663 and Helm 41593479576 succeeded. [GitHub Release 1.32.4](https://github.com/openstack-afterglow/openstack-afterglow/releases/tag/1.32.4).
- Release and latest OCI digest and revision match for API `sha256:04626f88e986f962a6ae30151accce08b5b984026da513a4954e66007364d217`, frontend `sha256:389982e1ddd32f9dd290cdff2a058cd6f7797c217fcdd942b00c21f359f5cf64`, worker `sha256:f6e05970539a203fd3c02dafc5b1e929a4a848903b93309e141a8003df48b982`. Digest-pinned linux/amd64 non-root version 1.32.4 and Helm chart version/appVersion 1.32.4 observed.
- Operational rollout remains blocked: SQL105 email tables are absent, restricted grant policy requests returned 503 without sufficient detail to identify the failing boundary, and current cold recovery/writer fencing is not qualified. The API image was smoke-tested with lifespan off; startup against production was not tested.
