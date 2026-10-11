## Implementation Tasks

- [x] Read the WireGuard Windows README and verified PowerShell example; trace user, synchronous and administrator provisioning plus image/volume metadata.
- [ ] Implement project-bound Windows password preflight, safe PowerShell generation and config-drive delivery in all instance-create paths without changing ordinary SSH deployment.
- [ ] Add supported-image/volume password and confirmation UI, readiness/review/progress and secret draft lifecycle in the shared wizard with ko/en/ja/zh-CN text.
- [ ] Add and run consumer-visible regression coverage for metadata admission, escaping/input boundaries, secret redaction and wizard transitions; run the instances target and required frontend checks.
- [ ] Exercise actual HTTP/native Nova SDK delivery with a loopback provider and the compiled UI in Chromium; record the synthetic/provider and live-guest verification boundaries.
- [ ] Update affected API/user/design/architecture/changelog docs, record scoped architecture guards and archive the completed change.
