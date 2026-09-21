## Why

The dev Compose manifest points Palimpsest Hub builds at `../palimpsest/hub/Dockerfile`, but the current sibling repository owns `docker/hub/Dockerfile`. That Dockerfile copies `hub/src` and `hub/{pyproject.toml,uv.lock}`, so its required build context is the Palimpsest repository root. Docker therefore aborts before building the requested Afterglow services because `backend` depends on `palimpsest-api`.

## What Changes

- Restore the Palimpsest API/bootstrap/worker build context to `../palimpsest` and Dockerfile path to `docker/hub/Dockerfile`.
- Align the local-services sibling preflight with the same canonical file.
- Correct architecture and deployment documentation that currently assert the inverse path contract.
- Verify the resolved Compose graph, build both Palimpsest Hub targets, and rerun the reported backend/frontend recreation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- Local source Compose builds resolve Palimpsest Hub from the sibling repository's canonical Dockerfile and repository-root context.

## Impact

Only local source-build configuration, its preflight, and associated documentation change. Service names, image names, ports, volumes, dependency ordering, runtime commands, credentials, and production image-pull configuration remain unchanged.
