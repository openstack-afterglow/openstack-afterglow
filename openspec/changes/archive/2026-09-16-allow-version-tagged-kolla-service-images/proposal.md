# Allow Version-Tagged Kolla Service Images

## Why

Waygate (and Palimpsest) Kolla image precheck rejected any remote image reference that was not pinned with a sha256 digest (`@sha256:<64-hex>`). Operators deploying with explicit version tags (e.g., `:v1.21.0` or `:1.0.0`) encountered validation failures (`invalid Waygate image reference; expected registry/repository@sha256:<64-lowercase-hex>`), even though release version tags are standard across Afterglow components. While `:latest` must continue to be prohibited to prevent multi-controller version divergence, explicit non-latest version tags should be permitted alongside immutable digests.

## What Changes

- Update `validate_image_ref.py` for Waygate and Palimpsest to accept remote references with explicit version tags (e.g., `registry/repository:<tag>`) as well as immutable sha256 digests (`registry/repository@sha256:<64-hex>`).
- Explicitly reject `:latest` (case-insensitive) and bare references without tags or digests.
- Preserve local source-build reference validation (`afterglow-local/...:<12-hex>`).
- Update and extend regression tests in `test_kolla_waygate_image_ref.py` and ensure Palimpsest validation coverage.

## Capabilities

### Modified Capabilities

- Remote Kolla image reference validation for Waygate and Palimpsest accepts explicit non-latest version tags in addition to sha256 digests.
- Bare image references and `:latest` tags continue to be rejected with clear validation error messages.

## Impact

Operators can deploy Waygate and Palimpsest using explicit release version tags (e.g. `ghcr.io/openstack-afterglow/waygate-api:v1.21.0`) without being forced to look up and pin raw sha256 digests, while retaining safety against unintended `:latest` tag usage.
