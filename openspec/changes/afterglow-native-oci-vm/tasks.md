## Implementation

- [x] 1. Confirm the user's selection of Linux amd64/KVM OCI-root rather than a baked conventional VM or chroot diagnostic.
- [x] 2. Inspect canonical application image/dependency/configuration and Palimpsest root/network/lifecycle contracts; preserve existing user changes and running resources.
- [x] 3. Implement the explicit native-vm image target and non-root direct-service startup, private initialization, persistence, failure handling and graceful shutdown.

## Verification

- [x] 4. Build affected native-vm images and execute actual application/DB/cache/worker readiness and persistence/shutdown smoke; check architecture and absence of guest container-engine requirements (arm64 and emulated amd64 image smoke; standard amd64 OCI export with 22 layers).
- [x] 5. Run scoped deterministic consumer-visible startup/lifecycle regressions and relevant existing checks (15 focused, 3,538 safe backend unit; scoped Ruff; architecture working guard).
- [ ] 6. Establish a current authorized Linux amd64/KVM target, qualified kernel/config/packer and exact resource scope without credential/admin bypass.
- [ ] 7. Boot the built OCI archive through public Palimpsest run, verify authenticated actual-root identity, direct service processes and HTTP/browser readiness, then safe owned lifecycle and retained-root persistence.
- [x] 7a. Additional conventional contract (does not satisfy 6/7): `native-cloud-vm` raw disk exported from the native OCI root and booted directly on Nova in the approved SYSTEM project with systemd/supervisor/HTTP/schema, Cinder/CephFS/RGW, reboot persistence, member login and exact-owned cleanup (2026-10-06).

## Delivery

- [x] 8a. Update affected architecture/deployment/changelog with observed evidence and explicit unverified boundaries; preserve user-owned files. Working guard reviewed source; staged guard currently covers unchanged baseline only.
- [ ] 8b. Archive only after native acceptance passes. Credential/qualified-target/resource approval and actual-root proof remain blocked.
