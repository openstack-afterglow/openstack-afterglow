## Context

Kolla starts a Uvicorn factory per controller; every process initializes independent database pools and background tasks.

## Goals / Non-Goals

Provide per-host process count configuration with existing single-worker behavior as default. Do not change ASGI server, operational deployment, or assert a performance gain.

## Decisions

Use `afterglow_backend_workers` (default 1), validate a positive decimal integer before lifecycle actions that render or activate the service, and pass `--workers` to the existing factory command. Preserve all proxy and host settings. Operators must assess database connections, distributed worker coordination and long-lived streams before a rollout.

## Risks / Trade-offs

Additional processes multiply pools, memory and startup/background work. Streaming connections can be interrupted during restart. Qualification uses isolated runtime only; production reconfiguration requires separate authorization.
