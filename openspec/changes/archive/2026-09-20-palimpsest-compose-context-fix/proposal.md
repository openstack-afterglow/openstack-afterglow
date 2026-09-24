# Palimpsest Compose build context fix

## Goal

Restore the local development Palimpsest Hub build by pointing Docker Compose at the current sibling repository layout.

## Why

`docker-compose.dev.yml` still resolves `../palimpsest/docker/hub/Dockerfile`, but the checked-out Hub image now owns `hub/Dockerfile` and its build context must be `../palimpsest/hub`. Docker therefore fails before any service starts with an `lstat .../palimpsest/docker` error.

## What Changes

- Update the three Palimpsest Hub Compose build definitions.
- Update the local-services sibling-source preflight to validate the same Dockerfile path.
- Verify the resolved Compose build graph and build both Hub image targets against the sibling source.
- Do not alter images, service names, volumes, credentials, or runtime behavior.
