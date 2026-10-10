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

### Requirement: Service-prefixed Compose database selection

`docker-compose.dev.yml` SHALL select each service's internal `DATABASE_URL` from `AFTERGLOW_DATABASE_URL`, `DROVER_DATABASE_URL`, `LUMEN_DATABASE_URL`, `WAYGATE_DATABASE_URL` or `PALIMPSEST_DATABASE_URL` in the selected env file or shell. Shell values SHALL take precedence. All API, worker and migration/bootstrap consumers of one service SHALL use the same destination. Unset or empty named inputs SHALL retain that service's canonical local database; generic `DATABASE_URL` SHALL NOT select a destination. Production and standalone Afterglow Compose SHALL require a nonempty `AFTERGLOW_DATABASE_URL` without a generic alias or local fallback.

The local runner SHALL accept explicitly selected external destinations and preserve resolved credentials, including literal dollar signs, in `.local-services/compose.env` with mode `0600` without logging them. Redis, Lumen checkpointer, local ports, networks, existing volume identities and encryption keys SHALL remain independently protected; choosing an external database SHALL NOT import or synchronize these companion stores.

#### Scenario: Selecting a service's database from dotenv or the shell

- **WHEN** an operator provides one named database URL in `.env`, an explicit env file or the shell
- **THEN** only that owner's consumers use the selected destination
- **AND** unrelated services keep their own selections or local fallback

#### Scenario: Preserving the prepared destination

- **WHEN** development Compose uses `.local-services/compose.env` after the original input file is removed or changed
- **THEN** its prepared database destinations and credentials are preserved exactly
- **AND** a newly provided shell value still takes precedence

#### Scenario: Empty or generic input

- **WHEN** a development service's named input is unset or empty, including an empty shell override
- **THEN** its canonical local database is used even if generic `DATABASE_URL` is external
- **AND** the same missing Afterglow input is rejected in production or standalone Compose

### Requirement: Database qualification separates direct access from production compatibility

Operators SHALL evaluate actual deployed images, schema ledgers/checksums, restored production snapshots, both old-writer/new-schema and new-writer/old-schema behavior, encryption-key continuity, companion state, mixed API/worker versions and rollback/restore limits whenever database-affecting work is assessed. Selecting the same database SHALL be described as direct shared access, not replication or synchronization. A connection or disposable smoke SHALL NOT be represented as production data/schema compatibility. Production writes and migration/bootstrap execution SHALL require independent approval and backup/restore evidence; migration runners that create ledgers or invoke `create_all` SHALL NOT be used as read-only inspection tools.

#### Scenario: Production evidence is unavailable

- **WHEN** deployed schema/image or restored-snapshot compatibility evidence is unavailable
- **THEN** the result explicitly records the missing evidence and leaves production compatibility unqualified
- **AND** verification uses disposable destinations without mutating production data

#### Scenario: Mixed writer or rollback incompatibility

- **WHEN** either writer/schema direction or the backup/restore path is incompatible or unproven
- **THEN** the qualification records that limitation instead of assuming migrations, bootstrap or changing the URL makes rollback safe

