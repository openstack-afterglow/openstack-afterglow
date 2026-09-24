## Why

The backend image downloads the OpenTofu `linux_amd64` archive unconditionally and performs the GitHub release fetch once inside the same layer as the large runtime package installation. Native Apple Silicon development builds therefore select the wrong OpenTofu artifact, and a transient GitHub 5xx response discards the completed package work and aborts `docker compose ... --build`.

## What Changes

- Select the OpenTofu Linux archive from BuildKit's `TARGETARCH` for supported `amd64` and `arm64` builds.
- Download the archive with bounded retries and verify it against the architecture-specific SHA-256 pinned from the official release manifest before installation.
- Isolate OpenTofu acquisition in a small build stage so transient release-download failures do not invalidate the backend runtime package layer.
- Document the native development-build architecture and verified-download contract.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- Backend container source builds install a verified, architecture-matching OpenTofu binary on both supported native development architectures.

## Impact

The change affects only backend image construction and build documentation. Runtime APIs, Compose service topology, application dependencies, credentials, ports, and production image selection remain unchanged. Unsupported BuildKit architectures fail explicitly instead of receiving an incompatible binary.
