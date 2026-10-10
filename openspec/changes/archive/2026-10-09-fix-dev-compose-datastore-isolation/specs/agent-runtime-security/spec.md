## ADDED Requirements

### Requirement: Development datastore destinations ignore generic environment overrides

`docker-compose.dev.yml` SHALL keep API, worker and migration/bootstrap database destinations local to the `afterglow-local-services` project. Repository `.env`, an explicit private Compose env file and shell variables named `DATABASE_URL`, `AFTERGLOW_DATABASE_URL`, `WAYGATE_DATABASE_URL`, `DROVER_DATABASE_URL`, `LUMEN_DATABASE_URL` or `PALIMPSEST_DATABASE_URL` SHALL NOT redirect those processes to external databases. Backend and Notion worker SHALL use the `afterglow` schema on `afterglow-mariadb`; sibling services SHALL use their own schema on `service-mariadb`. Lumen checkpointer and Redis remain local. Recovery SHALL preserve existing volume identities, encryption keys and applied migration hashes rather than deleting databases or changing remote credentials.

#### Scenario: Starting development Compose with production database variables

- **WHEN** plain development Compose loads database overrides from `.env` or the process environment
- **THEN** API, worker and migration/bootstrap `DATABASE_URL` values still target the canonical local schemas

#### Scenario: Starting development Compose with its prepared private env file

- **WHEN** development Compose uses `.local-services/compose.env` while remote database overrides remain in the process environment or container env file
- **THEN** API, worker and migration/bootstrap destinations remain local and the existing project volumes and encryption keys are reused
