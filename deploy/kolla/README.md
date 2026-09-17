# Afterglow Kolla-Ansible Service Deployment Guide

This guide deploys **Afterglow**, **Drover**, **Lumen**, **Waygate**, and **Palimpsest** through
the ordinary Kolla command line from `/etc/kolla`.

After the one-time setup below, activate the Kolla environment and deploy:

```bash
source /etc/kolla/.venv/bin/activate
cd /etc/kolla
kolla-ansible deploy -i multinode
```

The command runs stock Kolla services and enabled plugin services. Afterglow's
installed `site.yml` import dispatches the package-owned Lumen role, including
DB/Keystone prerequisites, PostgreSQL, migrations, API/worker startup and HAProxy.
Custom service and HAProxy plays declare `become: true`; the deployment SSH user
must already have noninteractive sudo on the relevant hosts. No CLI `--become`,
custom playbook argument, extra-vars file or shell wrapper is needed. This does
not grant sudo or change global Ansible settings.
---

## Architecture & Integration Principles

1. **Standard Kolla Invocation**:
   - The installer appends one marker-delimited `afterglow-site.yml` import to
     Kolla's installed `site.yml`. It refuses malformed or unexpected markers.
   - It links Kolla's default `all-in-one` inventory path to `/etc/kolla/multinode`
     and also links `group_vars` and `host_vars`, preserving normal Kolla
     inventory variable discovery.
2. **Plugin-owned Variables**:
   - Settings and secrets remain in `/etc/kolla/config/afterglow/globals.yml`
     (mode `0640`) and `/etc/kolla/config/afterglow/secrets.yml` (mode `0600`).
   - The installer links both files into Kolla's native `globals.d` loader;
     no `-e @...` arguments are required. It does not copy secret values.
   - Both files must be readable by the user that runs `kolla-ansible`; run
     the installer as that same deployment user.
3. **Kolla HAProxy Internal-VIP Listeners**:
   - HAProxy owns the internal-VIP frontend ports:
     - **Afterglow UI**: `3080`
     - **Afterglow API**: `8000`
     - **Waygate**: `8010`
     - **Drover**: `8011`
     - **Lumen**: `8012`
     - **Palimpsest**: `8020`
   - App containers bind the controller API addresses only, using private upstream ports `18081`, `18000`, `18010`, `18011`, `18012`, and `18020`. HAProxy balances each frontend across its matching controller group.
   - A tag-selected plugin run reconciles the matching Kolla HAProxy fragments.
     Kolla recreates HAProxy only if their resulting configuration hash changes.
   - The plugin does not create external-VIP routes, DNS records, or TLS certificates. Existing Drover and Waygate public catalog URLs remain operator-owned ingress contracts.
4. **Published GHCR Images**:
   - Services pull published `ghcr.io/openstack-afterglow/*` images using explicit release version tags (e.g. `:0.1.0`, `:0.2.20`, `:0.2.1`, `:v1.22.0`) or exact linux/amd64 manifest digests (`@sha256:...`).
   - Mutable tags such as `latest` or bare unpinned references are prohibited by role precheck validators to prevent multi-controller divergence.
   - Source-build mode remains an optional development path; it is not used for production deployment.
5. **Datastores & Credential Reuse**:
   - **MariaDB**: Creates plugin-owned `_kolla` schemas (`afterglow_kolla`, `drover_kolla`, `lumen_kolla`, `waygate_kolla`, `palimpsest_kolla`).
   - **Valkey (Redis)**: Current Kolla deploys Valkey server+Sentinel. Afterglow gives its Redis client every Kolla Sentinel address and the Kolla monitor name, so cache/session writes follow a promoted master without rewriting configuration; the generated `redis_url` still carries the existing master password and service DB index. The plugin creates no Redis container, so a full or Valkey-tagged Kolla deployment (`enable_valkey: "yes"`) must establish Valkey before plugin-only tagged operations. Other plugin services retain the connection behavior defined by their own roles. Explicit service indexes remain (5: Afterglow, 6: Waygate, 7: Drover, 8: Lumen, 9: Palimpsest).
   - **Palimpsest Hub**: Standalone layer repository service (API & worker) separate from Afterglow-owned layer build/consume APIs. Bootstrap executes `palimpsest-hub-bootstrap`; data migration (`palimpsest-hub-migrate-data`) is not run automatically and requires an empty-destination precondition.
   - **Lumen PostgreSQL**: Set `lumen_postgres_mode: bundled` to create the plugin-owned `lumen_postgres` container (`pgvector/pgvector:0.8.6-pg16@sha256:a3625087...`) on the first Lumen controller, or `external` to connect to an explicitly configured operator-managed PostgreSQL endpoint. External mode does not create a persistent PostgreSQL server container; it starts a disposable verification client container, runs an authenticated `SELECT 1`, then removes it.

---

## Installation & Symlink Creation

> **Prerequisite:** Complete [Operator Environment & Package Setup](#operator-environment--package-setup) and [Configuration Setup](#configuration-setup)
> first. `install.sh` validates both plugin variable files before changing
> Kolla's installation tree.

Run `install.sh` to add the standard-command wiring:

```bash
# Auto-detect Kolla binary/directory or pass explicit paths
KOLLA_ANSIBLE_BIN=/etc/kolla/.venv/bin/kolla-ansible \
KOLLA_ANSIBLE_DIR=/etc/kolla/.venv/share/kolla-ansible \
./deploy/kolla/install.sh
```

### Installer-managed artifacts
- Source role link under `$KOLLA_DIR/ansible/roles/`: `afterglow`.
- Verified package-installed roles under `$KOLLA_DIR/ansible/roles/`: `drover`
  (via `drover-kolla`), `lumen` (via `lumen-kolla`), `waygate` (via `waygate-kolla`),
  and `palimpsest` (via `palimpsest-kolla`). Installer validates non-symlink
  role paths and required lifecycle files.
- Aggregate playbook: `$KOLLA_DIR/ansible/afterglow-site.yml` ->
  `deploy/kolla/site.yml`.
- One marker-delimited `afterglow-site.yml` import in
  `$KOLLA_DIR/ansible/site.yml`.
- Default inventory link:
  `/etc/kolla/ansible/inventory/all-in-one` -> `/etc/kolla/multinode`.
- Inventory-variable directory links:
  `/etc/kolla/ansible/inventory/{group_vars,host_vars}` when their
  `/etc/kolla/{group_vars,host_vars}` sources exist.
- `globals.d` links:
  `90-openstack-afterglow-globals.yml` and
  `91-openstack-afterglow-secrets.yml`.
- An exact legacy duplicate of plugin globals is removed from stock
  `globals.yml` only after a parsed-mapping equality check; the original is
  retained as `globals.yml.before-afterglow-dedup`.

*Safety Check*: If any managed target conflicts or a `site.yml` marker is
unexpected, `install.sh` aborts rather than replacing it.

---

## Operator Environment & Package Setup

The `deploy/kolla/operator/` directory contains a canonical `uv` project
(`pyproject.toml` and committed `uv.lock`) specifying exact dependency pins:

- **`kolla-ansible`**: git commit `34daacfbf2d5987f543787f57535b2bebe7dee19` (21.2.0).
- **`drover-kolla`**: Git source `v0.2.21` (`subdirectory = "deploy/kolla"`).
- **`lumen-kolla`**: Git source `v0.2.1` (`subdirectory = "deploy/kolla"`).
- **`waygate-kolla`**: Git source `v0.1.2` (`subdirectory = "deploy/kolla"`).
- **`palimpsest-kolla`**: Git source `v0.1.3` (`subdirectory = "deploy/kolla"`).

### 1. Legacy Symlink Migration

If upgrading an environment that previously used Afterglow's source role symlinks for Drover, Lumen, Waygate, or Palimpsest, verify and remove only symlinks targeting the legacy Afterglow checkout before syncing packages:

```bash
# Verify and remove only legacy Afterglow source role symlinks if present
for role in drover lumen waygate palimpsest; do
  role_target="/etc/kolla/.venv/share/kolla-ansible/ansible/roles/$role"
  if [[ -L "$role_target" ]]; then
    link_dest=$(readlink "$role_target" || true)
    if [[ "$link_dest" == *"/deploy/kolla/ansible/roles/$role" ]]; then
      rm -- "$role_target"
      echo "Removed legacy $role symlink ($link_dest)"
    else
      echo "WARNING: Unexpected symlink at $role_target -> $link_dest (not an Afterglow source role; skipping)"
    fi
  fi
done
```

`install.sh` fail-closes with explicit migration instructions if a legacy symlink remains.

### 2. Operator Virtual Environment Sync

To sync the operator environment into Kolla's virtual environment:

```bash
cd deploy/kolla/operator
UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --frozen --inexact --no-install-project
```

This targets the actual Kolla environment, installs the role wheels as real
package-owned directories, and preserves unrelated installed operator packages
with `--inexact`. `--no-install-project` avoids treating this dependency-only
operator manifest as an application package. Review the pinned Kolla version
before synchronizing an existing cloud; package synchronization is a one-time
setup/update operation, not part of every deploy.

> **Security Note:** Keep the operator project free of live secrets or deployment globals. Operator configuration belongs exclusively in `/etc/kolla/config/afterglow/`.
Alternatively, packages can be installed directly via `pip` or `uv pip` into `/etc/kolla/.venv`:

```bash
/etc/kolla/.venv/bin/pip install \
  "git+https://opendev.org/openstack/kolla-ansible.git@34daacfbf2d5987f543787f57535b2bebe7dee19" \
  "git+https://github.com/openstack-afterglow/drover.git@v0.2.21#subdirectory=deploy/kolla" \
  "git+https://github.com/openstack-afterglow/lumen.git@v0.2.1#subdirectory=deploy/kolla" \
  "git+https://github.com/openstack-afterglow/waygate.git@v0.1.2#subdirectory=deploy/kolla" \
  "git+https://github.com/openstack-afterglow/palimpsest.git@v0.1.3#subdirectory=deploy/kolla"
```

### 3. Installation & Registration Order

Follow this installation sequence:

1. **Sync Operator Packages**: Run the explicit-environment command above in `deploy/kolla/operator`.
2. **Configure Operator Variables**: Populate `/etc/kolla/config/afterglow/globals.yml` and `secrets.yml`.
3. **Run Integration Installer**: Run `./deploy/kolla/install.sh`.

The installer validates that `$ROLES_DIR/{drover,lumen,waygate,palimpsest}` are valid package-installed directories (and not symlinks), wires the source role symlink (`afterglow`), and appends the `afterglow-site.yml` import to stock `site.yml`.

---

## Configuration Setup

1. **Create Plugin Configuration Root**:
   ```bash
   sudo install -d -m 0700 -o "$(id -un)" -g "$(id -gn)" \
     /etc/kolla/config/afterglow
   ```
2. **Create Globals (`/etc/kolla/config/afterglow/globals.yml`, mode `0640`)**:
   ```bash
   sudo install -m 0640 -o "$(id -un)" -g "$(id -gn)" \
     deploy/kolla/globals.afterglow.sample.yml \
     /etc/kolla/config/afterglow/globals.yml
   ```
   Customize the installed file for the deployment.
3. **Create Secrets (`/etc/kolla/config/afterglow/secrets.yml`, mode `0600`)**:
   ```bash
   sudo install -m 0600 -o "$(id -un)" -g "$(id -gn)" \
     deploy/kolla/passwords.afterglow.additions.yml \
     /etc/kolla/config/afterglow/secrets.yml
   ```
   Populate generated 64-hex keys and database/Keystone passwords without
   printing or committing them.

These two files are sufficient for a normal deployment. The role derives the
service topology and required runtime values from Kolla plus the plugin
globals/secrets, then generates and mounts the configuration needed by each
Afterglow process. A separate operator TOML is optional.
On the Kolla deployment host, `/etc/kolla/config/afterglow` is the single
plugin input root: `globals.yml` and `secrets.yml` sit at its top level, while
`backend/` and `frontend/` hold the optional operator TOML inputs described
below. On each Afterglow target host, the role separately renders runtime
layers under `/etc/kolla/config/afterglow/generated/`; do not copy the
deployment-host variable files to target hosts.


### Optional Detailed Afterglow Configuration

For settings not modeled as Kolla variables, place a partial or complete
backend TOML at `/etc/kolla/config/afterglow/backend/afterglow.conf` on the
Kolla deployment host. The role uses this path by default. The file may contain
only the detailed keys being overridden; it does not need to repeat generated
OpenStack, database, Redis, port, URL, or service-toggle values. Keep it outside
the repository and Kolla globals files, mode `0600`:

```bash
# The Kolla deployment user must be able to read this 0600 source file.
sudo install -d -m 0700 -o "$(id -un)" -g "$(id -gn)" \
  /etc/kolla/config/afterglow/backend /etc/kolla/config/afterglow/frontend
sudo install -m 0600 -o "$(id -un)" -g "$(id -gn)" ./afterglow.conf \
  /etc/kolla/config/afterglow/backend/afterglow.conf
```

An optional `/etc/kolla/config/afterglow/frontend/afterglow.conf` supplies
additional browser-safe values. Both default source files are discovered by
existence; no globals override is required. Override
`afterglow_operator_config_source` or
`afterglow_operator_frontend_config_source` only when an input lives elsewhere.
Missing inputs produce empty generated layers.

The role reads the backend source only to produce a protected short-lived
staging artifact. It removes `[builder].ssh_private_key` before TOML validation.
The GitLab OIDC client secret remains in this protected TOML flow and is not
shadowed by an empty container environment variable. The frontend source is
projected through the same closed browser-safe allowlist as the final frontend
configuration. Raw operator files are never mounted into containers.

Set `afterglow_ceph_monitors` in `globals.yml` from the `mon_host` value in
the deployed `/etc/kolla/config/ceph/ceph.conf`; this value is required by the
Afterglow precheck and final Kolla configuration layer.

The role writes process-specific runtime artifacts under
`/etc/kolla/config/afterglow/generated`:

1. generated `afterglow.generated.conf` base from Kolla and plugin globals/secrets;
2. sanitized `afterglow.operator.generated.conf` application override;
3. projected `afterglow.frontend.operator.generated.conf` public override;
4. generated `afterglow.zz-kolla.generated.conf` final override;
5. generated `afterglow.frontend.generated.conf`, a closed public projection of
   the merged base → backend operator → frontend operator → final result.

The backend and workers mount the generated base, sanitized backend operator,
and final override in that order. The final layer intentionally reasserts
deployment-owned OpenStack credentials/project/region/interface, database and
Redis connections, service toggles, public API/origin and CORS values,
encryption keys, Manila storage bindings, and application ports.

The frontend mounts only `afterglow.frontend.generated.conf`. Its allowlist
includes branding, refresh interval, public API/UI origins, service flags,
public S3/Grafana/chat/GitLab/MCP origins, and no credentials. Kolla-owned final
values win over both operator inputs.

### Kolla Shared Connection Inputs

Do not duplicate Kolla control-plane topology or administrative credentials in
the plugin files. Each service derives its MariaDB host, port, administrative
user, and administrative password from Kolla's `database_address`,
`database_port`, `database_user`, and `database_password`. The plugin secrets
file contains only each service's own schema-user password.

Afterglow derives its Valkey credentials and DB index from
`valkey_master_password` and `afterglow_redis_db_index`, then derives the
Sentinel monitor name, port, and complete host list from
`valkey_sentinel_monitor_name`, `valkey_sentinel_port`, and every member of
Kolla's `valkey` group. The generated `redis_url` remains the source of
username, password, and DB selection; its first-controller hostname is only a
seed value when Sentinel mode is enabled. Runtime reads and writes resolve the
current master through Sentinel, so a Kolla promotion does not require an
Afterglow reconfigure.

Other plugin services keep the Valkey connection behavior implemented by their
own roles. All plugin paths reuse Kolla's password file and create no separate
Redis container. A full or Valkey-tagged Kolla deployment
(`enable_valkey: "yes"`) must establish server and Sentinel state before
plugin-only tagged operations.

Runtime OpenStack settings use Kolla's `keystone_internal_url`, project/user
domain, region, and internal interface variables. Kolla's `openstack_auth`
provisions service projects/users; the matching runtime service-user passwords
remain in `/etc/kolla/config/afterglow/secrets.yml`. This follows the internal
Keystone configuration pattern used by Nova and Glance.
Secrets remain in `/etc/kolla/config/afterglow/secrets.yml`; do not put them in
`globals.yml` or commit the operator file.

`[builder].ssh_private_key` in legacy configuration files is not a supported
runtime setting and is deliberately not transferred. Provision a builder key
only through a future declared secret mount that is consumed by the runtime.
`config.gpu.toml` is also not copied independently; place its supported
settings in the operator TOML file until that file has an explicit handoff.

Re-run Afterglow with the standard Kolla command after changing globals,
secrets, or the optional operator file. All generated and imported
configuration artifacts participate in the container configuration hash, so
the affected processes are recreated with the updated settings:

```bash
cd /etc/kolla
kolla-ansible reconfigure --tags afterglow
```

### Afterglow Public Frontend Endpoint

Set `afterglow_public_endpoint_url` to the browser-facing HTTP(S) origin without a path. The role renders it into the frontend `ORIGIN`, backend CORS origin, frontend base URL, OAuth callback, and instance-health callback base. The DMSLab configuration uses `https://cloud.dmslab.re.kr`.

`afterglow_public_api_base` is the browser API origin. DMSLab's ingress routes `https://cloud.dmslab.re.kr/api/v1` to the backend, so it uses the same HTTPS origin and avoids mixed-content requests.

### Kolla External HAProxy Route

Set `afterglow_public_haproxy_enabled: true` and
`afterglow_public_haproxy_fqdn` to publish the configured hostname through
Kolla's existing external VIP/TLS frontend. The plugin owns the added HAProxy
fragment and map entry: `/api/` is dispatched to the Afterglow API backend and
all other paths to the frontend backend. It neither patches stock Kolla
templates nor changes Kolla's certificate, DNS, external VIP, or global config.

The Kolla external TLS certificate must cover the configured hostname.

### Drover, Waygate, and Lumen Public HAProxy Routes

Each service's `<service>-api` HAProxy entry stays internal (bound to the
internal VIP), so `<service>_internal_endpoint_url`/`<service>_admin_endpoint_url`
keep working unchanged. Set `drover_public_haproxy_enabled: true` /
`waygate_public_haproxy_enabled: true` / `lumen_public_haproxy_enabled: true`
with the matching `*_public_haproxy_fqdn` to add a second `<service>-public`
HAProxy entry that publishes the API directly on Kolla's external VIP/TLS
frontend (no loopback router is needed since each service exposes a single
API path). Disabling the toggle removes the plugin-owned `.cfg` fragment and
external-frontend-map entry on the next `reconfigure`. The Kolla external TLS
certificate must cover each enabled hostname.

### Lumen PostgreSQL Mode

`lumen_postgres_mode` is an explicit mutually exclusive choice for Lumen's LangGraph checkpointer:

- `bundled`: this Kolla plugin role runs its isolated `lumen_postgres`
  container on the first Lumen controller and verifies an authenticated
  `SELECT 1`. Kolla 2025.2 has no stock PostgreSQL role.
- `external`: set `lumen_external_postgres_url` in
  `/etc/kolla/config/afterglow/secrets.yml` to one `postgresql://` (or `postgres://`)
  URL. The role creates no PostgreSQL resource, validates the URL, writes a
  temporary mode-0600 libpq service file, runs an authenticated `SELECT 1`,
  then deletes that file. The URL never appears in the `psql` command line.

`lumen_memory_pgvector_url` is a separate optional PostgreSQL URL for semantic
memory. It is required only when `lumen_enable_pgvector: true`; provide it in
the same secret file rather than splitting it into host, port, and password
variables.

Never point `lumen_external_postgres_url` or `lumen_memory_pgvector_url` at
Kolla MariaDB. PostgreSQL is required for these Lumen contracts.

## Standard Inventory and Commands

Add all five plugin groups (`afterglow`, `waygate`, `drover`, `lumen`, `palimpsest`) directly to `/etc/kolla/multinode`; this is the authoritative inventory used by ordinary Kolla commands. Then run the installer once from the plugin checkout:

```bash
KOLLA_ANSIBLE_BIN=/etc/kolla/.venv/bin/kolla-ansible \
KOLLA_ANSIBLE_DIR=/etc/kolla/.venv/share/kolla-ansible \
./deploy/kolla/install.sh
```

The installer fails rather than replacing conflicting links or unexpected `site.yml` marker content. If it finds a legacy second YAML document in `/etc/kolla/globals.yml`, it removes it only when its parsed mapping exactly matches `/etc/kolla/config/afterglow/globals.yml`, preserving a backup beside the stock file.

> **Note on Kolla Integration:** Stock Kolla-Ansible site playbooks do not auto-discover custom roles. Custom service roles execute through standard `kolla-ansible` commands only after `install.sh` appends the `afterglow-site.yml` import to Kolla's installed `site.yml`. Uninstalled environments will not execute custom roles automatically.

### Post-Installer Standard Kolla Commands

From `/etc/kolla`, once `install.sh` has integrated the plugin import into `site.yml`, standard bare `kolla-ansible` lifecycle commands run custom service operations against `/etc/kolla/multinode`:

```bash
# Pull plugin and stock service images (force-refreshes mutable tags)
kolla-ansible pull -i multinode

# Deployment of enabled stock and plugin services, including stock Valkey
kolla-ansible deploy -i multinode

# Reconfigure running services after config/globals changes (force-refreshes mutable tags)
kolla-ansible reconfigure -i multinode

# Upgrade services to new images and run policy seeding (force-refreshes mutable tags)
kolla-ansible upgrade -i multinode
```

Tag-filtered operations also remain supported:

```bash
# Reconfigure only Afterglow
kolla-ansible reconfigure -i multinode --tags afterglow

# Reconfigure all five plugin services
kolla-ansible reconfigure -i multinode --tags afterglow,waygate,drover,lumen,palimpsest
```

`-i multinode` explicitly selects `/etc/kolla/multinode` when run from
`/etc/kolla`. Omitting `-i` uses the installer's link to that same inventory.
Custom `-p` and `-e @...` arguments are diagnostic overrides, not normal setup.
With `--limit`, bootstrap and bundled PostgreSQL tasks can still delegate to the
first service controller. Its existing configuration and shared datastores must
be available; a limit does not isolate those dependencies.

### Verification and existing installations

```bash
kolla-ansible prechecks -i multinode --tags afterglow,lumen
kolla-ansible deploy -i multinode --tags afterglow,lumen
```

Check API/worker state on the selected controllers and test public HTTP routes.
An API liveness response does not prove DB, Redis, PostgreSQL or authenticated
application operations. Verify those dependencies as well. The role pin is
`lumen-kolla==0.2.0`; installation refuses a different version rather than
silently downgrading an existing deployment.

The canonical operator files are `config/afterglow/globals.yml` and
`config/afterglow/secrets.yml`. Before rerunning the installer on a legacy setup,
compare any regular files in `globals.d/90-*` or `globals.d/91-*` with those
canonical files. Preserve the active values and backups before reconciling
them; the installer intentionally refuses conflicting files and never merges
secrets implicitly. Do not replace live credentials with sample files.

For repository verification, `npm run test:kolla:contract` runs the offline
structure/installer contracts. After installing the operator environment,
`npm run test:kolla:runtime` exercises the native CLI and real Ansible with
isolated role fixtures, including privilege inheritance and negative controls.
It does not contact or mutate a cloud.

---

## Uninstallation & Role Ownership

```bash
./deploy/kolla/uninstall.sh
```

### Uninstaller Ownership Rules

- **Source Roles**: Removes installer-managed symlink for `afterglow`.
- **Stock Playbook**: Removes the `afterglow-site.yml` import block from `site.yml`.
- **Aggregate Playbook & Globals.d**: Removes aggregate playbook link and `globals.d` links.
- **Package-owned Roles**: `uninstall.sh` **never** deletes package-installed `drover`, `lumen`, `waygate`, or `palimpsest` role files under `$ROLES_DIR`. Package role lifecycle is managed via `uv` / package tooling.
- **Operator State**: Leaves `/etc/kolla/multinode`, plugin configuration, databases, containers, images, and source checkouts untouched.
