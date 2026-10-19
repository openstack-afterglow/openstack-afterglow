## Why

The requested i18n merge `cd3062158575034e24774d0b126bd1f1faedcd19` passes every GitHub test lane and compiles the frontend, but run 39252951448 fails in Dockerfile's Node20-Alpine runtime `npm install --omit=dev --ignore-scripts` with npm10.8.2 Arborist `Cannot read properties of null (reading 'edgesOut')`. The runtime copies only package.json and re-resolves dependencies rather than using the committed npm lock.

## What Changes

Copy the existing package-lock.json into the frontend runtime stage and use `npm ci --omit=dev --ignore-scripts`. Align only its two root version metadata fields with the existing 1.30.19 manifest. Keep the dependency graph, Bun build, runtime base, scripts, user and deployment unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

Frozen frontend runtime dependency installation from the repository's existing npm lock.

## Impact

Dockerfile frontend stage, npm lock version metadata and affected build/evidence documentation. Verify actual amd64/arm64 frontend images and HTTP locale smoke, full project gate, staged architecture guard and exact-SHA CI. Do not deploy production, change service config/data or include the shared checkout's other work.
