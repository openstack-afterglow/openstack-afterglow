# Agent Runtime and Security Specification

## Purpose

Preserve the repository's deployment, API-version, and tenant safety constraints outside the short entrypoint. Implementation sources and detailed deployment/API documents remain the authority for exact settings and operational state.

## Requirements

### Requirement: Compose modes remain isolated and non-destructive
`docker-compose.yml` SHALL define only the installed Afterglow frontend/backend with external DB/Redis/services. `docker-compose.dev.yml` SHALL be the source-build development environment and the only owner of the isolated `test` profile. `docker-compose.prod.yml` SHALL pull prebuilt GitHub/GHCR images, never build source or fall back to development HTTP/self-signed TLS/secret bypass; HAProxy terminates TLS and only trusted HTTPS overrides reach sibling services. Operators SHALL choose each file explicitly with `-f`; `npm run services:up` is the supported development entrypoint. Mode switches SHALL preserve existing projects, volumes and encryption keys; agents SHALL NOT run broad prune or `down --volumes`. Test datastore containers SHALL be started/stopped in the `afterglow-test` project only, on isolated loopback ports and tmpfs; they SHALL NOT delete development databases or require cloud credentials. Container health is not proof of authenticated dashboard/OpenStack behavior.

#### Scenario: Running local functional tests
- **WHEN** the test profile starts MariaDB, PostgreSQL and Redis
- **THEN** only the dedicated `afterglow-test` resources are managed and the development and production volumes remain untouched

### Requirement: Configuration changes stay synchronized and secrets stay secret
`afterglow.conf` SHALL be the sole base filename; local overrides use `afterglow.*.conf` and optional `config.gpu.toml`; the example is `afterglow.conf.example`. A configuration change SHALL update `backend/app/config.py` (`_load_toml` and `Settings`), `generate_k8s.py`, and the example together. Passwords, tokens and keys SHALL go through `render_secret()` to secret.yaml rather than ConfigMap, source, logs or error responses. Publication SHALL never include `.env` or real credentials.

#### Scenario: Adding a service token setting
- **WHEN** a token-backed setting is added to the backend
- **THEN** the example, loader and Kubernetes renderer agree, with only secret.yaml holding the rendered value

### Requirement: New APIs mount under `/api/v1` and verify ownership
A new router SHALL have no local prefix and SHALL be mounted in `backend/app/main.py` at `/api/v1/<resource>`; callers, tests and deployment rules use that path. Ownership-sensitive routes SHALL be registered in `_AUDIT_PREFIX_MAP` and check project ownership; admin routes SHALL use `Depends(require_admin)`. The only `/api` dual mounts are the baked cloud-init callbacks `POST /api/k3s/callback`, `POST /api/instances/{id}/health/report`, and `POST /api/instances/{id}/credentials/rotate-cephx`; `backend/tests/test_api_v1_legacy_compat.py` protects them.

#### Scenario: Adding a project-scoped endpoint
- **WHEN** a new resource router is introduced
- **THEN** it mounts only at `/api/v1`, performs caller/project checks and is registered in the audit map without expanding legacy `/api`

### Requirement: Execution and authentication boundaries fail closed
Execution-bound input SHALL use Pydantic allow-list validation; shell/cloud-init interpolation SHALL quote dynamic and external OpenStack values using `shlex.quote()` or Jinja2 `| shlex_quote`, and YAML values SHALL reject newline injection. Token binding, session blacklist, authorization and ownership failures SHALL deny access, not log-and-allow. The documented Redis outage exception for *login lockout only* SHALL NOT be generalized. Secret/HMAC/download-token comparisons SHALL use `hmac.compare_digest`; tests for new endpoints SHALL exercise authentication, ownership, injection-sensitive quoting and failure paths.

#### Scenario: Keystone or Redis denies a protected action
- **WHEN** token binding or ownership validation fails or throws
- **THEN** the protected endpoint denies the action and does not expose internal information or secrets to the client
