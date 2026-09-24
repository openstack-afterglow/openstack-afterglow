## 1. Root cause

- [x] Confirm the reported download failure and the hardcoded `linux_amd64` artifact conflict with native `arm64` builds.

## 2. Backend image

- [x] Add an architecture-aware, retrying, checksum-verified OpenTofu installer stage.
- [x] Copy the verified binary into the backend runtime image without retaining download tooling.

## 3. Documentation and verification

- [x] Update deployment documentation, changelog, and architecture review.
- [x] Build the backend image on the native architecture and verify `tofu version` inside it.
- [x] Run the required repository gate and staged architecture guard.
