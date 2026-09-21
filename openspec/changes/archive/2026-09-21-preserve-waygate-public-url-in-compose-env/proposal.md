## Why

`docker-compose.dev.yml` uses Compose's required-variable interpolation for `WAYGATE_PUBLIC_BASE_URL` in a shared environment anchor. Compose evaluates that anchor before service selection, so even targeted backend/frontend build or recreation commands fail while parsing the file. This prevents operators from rebuilding only Afterglow against already-running dependencies.

Waygate itself already validates `WAYGATE_CALLBACK_BASE_URL` at API and worker startup and rejects missing, malformed, credential-bearing, loopback, or unspecified URLs. Compose should not duplicate that validation globally at parse time.

## What Changes

- Let the development Compose file interpolate an unset Waygate public URL as an empty value so unrelated and `--no-deps` targeted commands can parse.
- Keep full local-stack preparation fail-closed in `local-services.mjs`, preserve the validated callback value in private `compose.env`, and retain the existing Waygate API/worker startup validation.
- Remove the functional test runner's fake `https://unused.invalid` interpolation workaround; actual disposable Compose startup becomes the regression proof.
- Document that targeted Afterglow-only recreation must use `--no-deps`; starting or recreating Waygate still requires a gateway-VM-reachable public URL.

## Impact

- Affects the development Compose manifest, local-services input handoff, functional Compose runner, local deployment documentation, changelog, and architecture evidence.
- Does not weaken Waygate runtime validation or production/Kolla configuration.
- Does not create a fake callback URL or silently substitute localhost/container DNS.
