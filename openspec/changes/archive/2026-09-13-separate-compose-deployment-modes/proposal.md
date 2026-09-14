## Why

The base Compose file currently mixes Afterglow defaults, development builds, independent service runtimes and optional infrastructure. Local deployment requires three files, while production still contains build directives and no mandatory TLS ingress. The requested deployment contract needs explicit, independently selectable base/dev/prod modes without losing existing local data.

## What Changes

- `docker-compose.yml` is a standalone two-service frontend/backend baseline using published Afterglow images and externally configured databases/cache/catalog services.
- `docker-compose.dev.yml` is the standalone current-source environment. It consolidates existing isolated local/source overlays, builds Afterglow and sibling Lumen/Waygate/Drover/Palimpsest API/worker images, uses local service DNS and isolated local datastores, and retains the current project and volume identities. Existing optional development profiles remain development-only where still applicable.
- `docker-compose.prod.yml` is image-pull-only and starts HAProxy TLS ingress/load balancing in front of Afterglow. Existing extracted-service deployment support remains optional with properly gated migrations; Afterglow communicates through authenticated Keystone catalog discovery, never dev DNS overrides. Certificates and production credentials are operator-supplied and fail closed.
- Update the development runner, deployment commands, repository rules, examples and behavioral deployment contracts; remove the obsolete local overlays and installed-image development fallback.
- Switch the current local deployment to the single dev manifest without deleting volumes, rotating keys, touching unrelated containers or changing remote OpenStack resources.

## Capabilities

### New Capabilities

- Explicit base/development/production Compose contracts with production TLS ingress and scalable DNS-resolved backend pools.

### Modified Capabilities

- Existing local source-build lifecycle and image-based production service deployment.

## Impact

No business API/schema changes are planned. Acceptance requires resolved Compose configuration checks, actual dev rebuild/readiness and authenticated BFF/dashboard smoke, actual HAProxy TLS/routing/load-balancing verification with disposable resources, relevant regression gates and architecture freshness. Nova currently returns HTTP 503 at its catalog endpoint; mode separation cannot manufacture healthy cloud responses. Verify it after cutover and report any remaining upstream blocker rather than suppressing the failure. No commit, push, production deployment or certificate issuance is authorized by this change.
