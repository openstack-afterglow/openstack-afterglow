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
   - `kolla-ansible reconfigure -i multinode --tag afterglow,lumen,drover,palimpsest,waygat` selects all five enabled services without a wrapper. `waygat` is an explicit Waygate selection tag, including its application image preparation and HAProxy tasks; `waygate` remains the canonical role/inventory name and also works as a tag.
   - A Kolla package reinstall can remove the installed stock-site import while leaving all role links valid. Rerun the official installer, then inspect this command with `--list-tasks`; successful stock-only output is a silent integration failure, not a custom-service rollout.
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
   - Application images follow the existing published `ghcr.io/openstack-afterglow/*:latest` channels through `afterglow_image_tag`, `drover_image_tag`, `waygate_image_tag`, `lumen_image_tag`, and `palimpsest_image_tag`. `stable` is also supported where that channel is published; this policy does not create new channels.
   - Each invocation resolves moving tags to exact registry manifest/index digests on the first targeted controller for each service, before role prechecks. All targeted controllers share that selection, including across serial batches; the next invocation resolves afresh.
   - Component enablement may differ by controller, including three Palimpsest APIs with one worker. Selection covers only components enabled on enabled published-mode service consumers; disabled and source-mode hosts do not contribute. Each controller receives only its locally enabled components from the same frozen selection.
   - Selection readiness is bound to its service. An earlier service's references cannot authorize an unprepared later published-image target when its first target is disabled or in source mode; split these target sets with `--limit`.
   - Explicit version or `@sha256:...` component `*_image_ref` pins remain available for controlled releases and rollback and skip registry lookup. Moving channels belong in `*_image_tag`, not mutable or bare `*_image_ref` overrides.
   - Effective component image/ref and service namespace/tag inputs are collected from their published consumers, preserving a pin on a later-only worker. Contradictory effective inputs for the same component fail before registry or credential access; reconcile them or split targets with `--limit`.
   - Source-build mode remains an optional development path; it is not used for production deployment. Stock Kolla images, datastore pins, Cloud Shell's multi-architecture digest requirement, and unmanaged Lumen sandbox images are unchanged.
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
- Verified root-package roles under `$KOLLA_DIR/ansible/roles/`: `drover`
  (via `drover==0.2.25`), `lumen` (via `lumen==0.3.1`), `waygate`
  (via `waygate==0.2.0`), and `palimpsest` (via
  `palimpsest-client==0.2.3`). Installer validates non-symlink role paths and
  required lifecycle files, and refuses a leftover retired `palimpsest-local`
  distribution that shares the Palimpsest role files.
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

`deploy/kolla/operator/pyproject.toml` is a dependency-only `uv` manifest for
`kolla-ansible` and the root service distributions:

- **`drover==0.2.25`** owns the `drover` role.
- **`lumen==0.3.1`** owns the `lumen` role.
- **`waygate==0.2.0`** owns the `waygate` role.
- **`palimpsest-client==0.2.3`** owns the `palimpsest` role (renamed from
  `palimpsest-local` in 0.2.3; see the operator README for migration).

All roots require Python 3.11 or newer. There are no `*-kolla` distributions,
no `subdirectory = "deploy/kolla"` sources, and no plugin role becomes a Kolla
default dependency merely by being installed.

Each root package promotion is bound to its immutable `vX.Y.Z` release tag.
The operator manifest records that tag by name; `operator/uv.lock` records the
resolved commit, so frozen synchronization gives every controller the same
artifact. Branches, bare Git URLs, mutable `latest` labels, and tag rewrites
are prohibited. The tag must exactly match root-package metadata and carry the
package-owned role. The scheduled Afterglow workflow opens a reviewed PR when
a newer eligible sibling tag appears; merging that PR is the promotion boundary.

### 1. Legacy Symlink Migration

If an older installation linked a sibling role to a known legacy Afterglow
checkout, remove only an **exact** match. Replace the placeholder with that
checkout's absolute path. A missing/relative path or any different link target
fails closed and leaves every link untouched:

```bash
legacy_afterglow_checkout=/absolute/path/to/the/legacy/afterglow
[[ "$legacy_afterglow_checkout" = /* && -d "$legacy_afterglow_checkout/deploy/kolla" ]] || {
  echo "Set legacy_afterglow_checkout to the known absolute Afterglow checkout." >&2
  exit 1
}

for role in drover lumen waygate palimpsest; do
  role_target="/etc/kolla/.venv/share/kolla-ansible/ansible/roles/$role"
  expected_target="$legacy_afterglow_checkout/deploy/kolla/ansible/roles/$role"
  if [[ -L "$role_target" ]]; then
    actual_target=$(readlink "$role_target" || true)
    if [[ "$actual_target" != "$expected_target" ]]; then
      echo "Refusing to remove unexpected $role_target -> $actual_target" >&2
      exit 1
    fi
    rm -- "$role_target"
    echo "Removed legacy $role symlink ($actual_target)"
  fi
done
```

### 2. Promote and Sync the Operator Dependencies

Do not make a Kolla control node discover a remote "latest" release at install
time. From a reviewed Afterglow checkout, the scheduled
`promote-kolla-role-tags` workflow (or its manual dispatch) records each new
eligible sibling `vX.Y.Z` tag by name and opens a promotion PR. Review and
merge that PR first; its lock is the release set to install.

Then, from the promoted checkout:

```bash
cd deploy/kolla/operator
UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --locked --inexact --no-install-project
```

`--no-install-project` is required: the operator manifest has dependencies but
no application package. `--inexact` preserves unrelated packages in the Kolla
environment. `--locked` asserts that `pyproject.toml` matches `uv.lock` and fails
if the manifest was edited without relocking, ensuring every controller installs
the exact reviewed commits.

### 3. Installation & Registration Order

1. **Sync root packages** with the explicit-environment command above.
2. **Configure operator variables** in `/etc/kolla/config/afterglow/globals.yml`
   and `secrets.yml`.
3. **Run the integration installer**: `./deploy/kolla/install.sh`.

The installer validates that `$ROLES_DIR/{drover,lumen,waygate,palimpsest}` are
package-owned directories (not symlinks), wires only the source `afterglow`
role symlink, and appends the `afterglow-site.yml` import to stock `site.yml`.

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
staging artifact. It validates the original TOML, removes `[builder].ssh_private_key`,
and validates the sanitized result.
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

#### Application-only debug diagnostics

The generated base provides `[DEFAULT]` / `debug = false`. To enable diagnostics,
add this partial TOML to the private backend operator source described above:

```toml
[DEFAULT]
debug = true

[logging]
log_level = "INFO"
```

Use exact, unquoted lowercase TOML `true` / `false`; `True` / `False` is invalid.
The sanitizer validates before copying and never silently rewrites invalid
booleans. Missing `[DEFAULT]` or `debug` remains compatible with default `false`.
The sanitized backend operator layer preserves the value, and the final Kolla
overlay intentionally does not reassert it. The frontend public allowlist omits
`DEFAULT` and logging settings; no browser debug toggle is added. No new Kolla
globals variable or container `DEBUG` default is needed.

An explicitly injected backend process `DEBUG=true` / `DEBUG=false` takes
precedence over TOML, including disabling a TOML `true`. A deployment-host shell
variable alone is not container injection. Debug enables only the `app` logger
namespace; `[logging].log_level` / `LOG_LEVEL` retains root/dependency control,
and protected HTTP/SDK/SQL/access loggers remain WARNING-clamped. Both output
handlers also reject propagated DEBUG/INFO records from these namespaces even
when a descendant explicitly enables DEBUG. Debug does not enable HTML tracebacks,
HTTP wire logging, authentication/authorization bypass,
insecure mode or secret output. Diagnostics are bounded route/outcome/source
metadata; request path values, queries, headers, bodies, cookies, exception text,
source lines, locals and chained causes are excluded. Sensitive keys and recognized
credential patterns are masked in full. Text secret assignments (including `key`,
`cephx_key`, `kube_config`, API-key/authorization variants, headers and bodies) redact
the remainder: spaces, nested JSON, escaped quotes and multiline values provide no
trusted boundary. Keep safe structure in bounded extra metadata, not string dumps.
Callers must log static events and bounded, code-owned metadata: heuristic text
masking is defense-in-depth, not permission to log arbitrary user text or full
request/response/configuration dumps. Opaque non-string messages, dictionary/extra
keys and builtin subclasses are omitted without invoking their representation;
extras exceeding the nesting limit are redacted. Reconfigure/restart the affected
consumers to apply the change.
See [the deployment guide](../../docs/en/deployment.md#application-diagnostics-defaultdebug)
for the other generation paths and precedence details.

### Palimpsest Hub endpoint and HAProxy routing

Use one trusted HTTPS origin for the Hub catalog endpoint, HAProxy hostname and
Afterglow package transport in `/etc/kolla/config/afterglow/globals.yml`:

Configure the BFF integration below. For public routing, copy the complete
guarded Palimpsest block from `globals.afterglow.sample.yml`.

```yaml
palimpsest_public_endpoint_url: "https://palimpsest.dmslab.re.kr"
afterglow_service_palimpsest_enabled: true
```

The sample derives `palimpsest_public_haproxy_fqdn` only from a valid HTTPS
origin, and its explicit exposure setting enables routing only when the URL
exactly matches that hostname (with an optional trailing slash). Invalid
origins and mismatched overrides therefore disable the sample's public map
even with the pinned 0.2.3 role. That older role does not provide the newer
HAProxy-only origin assertion; do not replace the sample predicate with an
unconditional `true` and assume that assertion exists.
The exposure toggle remains opt-in. Existing DNS, external HAProxy TLS and a
certificate covering the hostname are operator prerequisites, not created here.

Afterglow's `afterglow_service_palimpsest_internal_url` defaults to an explicitly
configured `palimpsest_public_endpoint_url`. When the integration is enabled and
this value is nonempty, both generated `[services]` layers emit
`palimpsest_internal_url`. A separate trusted HTTPS BFF endpoint can override
`afterglow_service_palimpsest_internal_url`. When it is empty or no Hub URL is
supplied, the role omits this key and preserves the detailed backend operator
TOML; it never invents an HTTP VIP or catalog fallback. A selected nonempty
Kolla URL wins over detailed TOML. An explicit `SERVICE_PALIMPSEST_INTERNAL_URL`
environment variable still wins at application load time.

Install the reviewed Afterglow role and, for hostname derivation without the
sample expression, the updated independently packaged Palimpsest role. Then
apply through the normal scoped command:

```bash
kolla-ansible reconfigure -i multinode --tags palimpsest,afterglow
```

Keep published API/worker image pins and the Hub volume intact. Routing does not
upgrade Hub APIs: native project packages require a compatible Hub serving
`/v1/projects/current`; legacy Hub 0.2.1 returns 404 even with working HAProxy.
Package public authority (`palimpsest_package_public_origin`, often the Afterglow
key-gateway origin), reader identity and protected IDs remain separate Hub inputs.
Verify the generated backend URL, TLS from each backend host, and authenticated
package context. `/v1/health` alone is not package acceptance.


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

### Global Cloud Shell

Cloud Shell is a Zun workload in an operator-owned dedicated project; it is not a long-running Kolla container. Before enabling it, create exactly one project. `afterglow_cloud_shell_network_id` is optional: leave it empty to use the dedicated project's default network (database default, then the existing automatic default-network policy, or the validated shared policy when automatic provisioning is disabled); the selected network needs a subnet and external network/router gateway connectivity, and explicit IDs must belong to the dedicated project. The security group defaults to that project's `default` group, resolved to one exact project-owned ID with its existing rules unchanged, so it is not egress-only; set an explicit project-owned group when stricter isolation is required. The role never creates or deletes the project, network, router, or security group. Set dedicated Cinder and Zun quotas on that project rather than changing tenant quotas.

Required plugin globals:

```yaml
afterglow_service_zun_enabled: true
afterglow_service_cloud_shell_enabled: true
afterglow_cloud_shell_project_name: "afterglow-cloud-shell"
afterglow_cloud_shell_project_id: "<dedicated-project-uuid>"
afterglow_cloud_shell_image: "ghcr.io/openstack-afterglow/afterglow-cloud-shell@sha256:<64-hex-digest>"
afterglow_cloud_shell_network_id: ""  # optional: empty uses the dedicated project's default network
afterglow_cloud_shell_security_group: "default"
afterglow_cloud_shell_auth_url: "https://keystone.example.com:5000/v3"
afterglow_cloud_shell_zun_websocket_origin: "wss://zun.example.com"
afterglow_cloud_shell_volume_type: "ceph"
```

Stock Kolla must also enable `enable_zun`, `enable_kuryr`, `enable_etcd`, `docker_configure_for_zun`, `containerd_configure_for_zun`, and `zun_configure_for_cinder_ceph`, with at least one host in `zun-compute`. The Cloud Shell image must be an immutable multi-architecture manifest digest accessible from every Zun compute host. The Zun API must support container microversion 1.36, and zun-compute must be able to attach Cinder (Ceph RBD) volumes and format them as ext4 on first mount.

`kolla-ansible prechecks -i multinode --tags afterglow` verifies that the dedicated project differs from the general Afterglow service project, that an explicit network belongs to it, that the security group resolves uniquely inside it by ID then name and belongs to it, that scoped Zun/Cinder calls succeed, and that every Zun compute can inspect the image. Keystone setup grants the existing Afterglow service user `admin` in the pre-created project; it does not provision the project or networking.

Disable `afterglow_service_cloud_shell_enabled` before rollback. Wait through the maximum session/reconciliation window and verify no managed Zun containers remain. Persistent home volumes are deliberately retained until the operator applies an explicit backup/deletion policy; remove the role assignment and dedicated project only after that decision. See [`docs/deployment.md`](../../docs/deployment.md#전역-cloud-shell-선택-배포) for runtime settings, verification, and rollback order.

### Kolla External HAProxy Route

Set `afterglow_public_haproxy_enabled: true` and
`afterglow_public_haproxy_fqdn` to publish the configured hostname through
Kolla's existing external VIP/TLS frontend. The plugin owns the added HAProxy
fragment and map entry: `/api/`, exact `/mcp`, `/mcp/` descendants, and
`/.well-known/` discovery go to the API; every other path goes to the frontend.
`/mcpevil`, `/mcp-other`, and `/oauth/mcp/authorize` stay on the frontend.
It neither patches stock Kolla
templates nor changes Kolla's certificate, DNS, external VIP, or global config.

The Kolla external TLS certificate must cover the configured hostname.

For DMSLab personal/OAuth MCP, configure:

```yaml
afterglow_service_mcp_enabled: true
afterglow_mcp_public_url: "https://cloud.dmslab.re.kr/mcp"
```

The empty role default does not overwrite operator `[mcp].public_url`; a
nonempty override is projected into both backend and the public frontend
configuration. Explicit resource paths, including a dedicated-host root, are
preserved rather than receiving an extra `/api/v1/mcp`. The built-in HAProxy
fragment supports the canonical shared-host `/mcp`; an operator choosing an
arbitrary different resource path must supply matching ingress routing.
Deploy the matching role/config/router as well as the images. Verify public
protected-resource and authorization-server metadata, initialize and every
tools/list page without redirects, then issue one owned key and revoke it.
This is connectivity/visible-tool proof, not tools/call or provider proof.

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
# Download plugin and stock service images without replacing running containers
kolla-ansible pull -i multinode

# Deployment of enabled stock and plugin services, including stock Valkey
kolla-ansible deploy -i multinode

# Reconfigure running services and apply this invocation's selected images
kolla-ansible reconfigure -i multinode

# Upgrade services to this invocation's selected images and run policy seeding
kolla-ansible upgrade -i multinode
```

For enabled, published-image plugin services, `prechecks`, `pull`, `deploy`,
`reconfigure`, and `upgrade` prepare exact image references before the
service-owned immutable-reference validators run. Registry selection reads
manifest metadata without downloading layers and fails closed on lookup errors;
it does not reuse a stale or locally cached channel selection. `pull` downloads
the selected images only. `deploy`, `reconfigure`, and `upgrade` replace running
containers when the selected image changes. A later command resolves channels
again, so a preceding `pull` does not pin its selection for a later deployment.

An explicit component `*_image_ref` version tag or digest is retained verbatim
and skips channel lookup for that component. Pin every enabled component when
an entire service must remain on a reviewed release or rollback. Disabled
services/components and source-build services do not perform channel lookup.

Tag-filtered operations also remain supported:

```bash
# Reconfigure only Afterglow
kolla-ansible reconfigure -i multinode --tags afterglow

# Reconfigure all five plugin services
kolla-ansible reconfigure -i multinode --tags afterglow,waygate,drover,lumen,palimpsest
```

Service tags select the corresponding image preparation and lifecycle tasks;
unselected services do not perform channel lookup. With `--limit`, selection
runs on the first controller actually targeted for that service, not an
excluded inventory controller. That selection is shared by every targeted
serial batch, even with `kolla_serial=1`.

Kolla's native globals loader and `-e` extra-vars outrank `set_fact`. The
integration refuses to dispatch when an effective `*_image_ref` overrides its
selected digest. Before migrating an existing installation, remove old mutable
(`:latest`/`:stable`) or bare `*_image_ref` entries from globals and extra-vars
files/arguments, and use the matching service `*_image_tag` instead. For example,
use `-e afterglow_image_tag=latest`, not
`-e afterglow_backend_image_ref=ghcr.io/openstack-afterglow/afterglow-api:latest`.
Keep `*_image_ref` overrides only for explicit immutable version or digest pins;
those continue to work through native `-e`.

Afterglow `deploy` and `reconfigure` run the one-shot schema bootstrap after
rendering configuration, before policy seeding and backend start. `upgrade`
bootstraps the pulled image against the existing generated configuration before
seeding or restarting. This creates missing ORM tables even when the running
backend sets `auto_create_tables=false`; a bootstrap failure stops the lifecycle
before an incompatible backend can start. `create_all` cannot add columns to
existing tables. Apply reviewed SQL migrations from `backend/migrations/manifest.txt`
before rollout whenever an existing table changes, and verify the authenticated
application path rather than treating `/health` as database readiness.

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
application operations. Verify those dependencies as well. The installer requires
the matching root distribution versions listed in [Operator Environment & Package
Setup](#operator-environment--package-setup) and refuses a mismatch rather than
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
isolated role fixtures, including privilege inheritance, negative controls and
published-consumer cases loading the actual `roles/afterglow/defaults/main.yml`.
It does not contact or mutate a cloud.

`node scripts/kolla-contract.test.js` checks the in-tree Afterglow role,
aggregate dispatch, and installer ownership boundary without sibling checkouts.
Its disposable installed-role fixtures use root-distribution metadata read by
the real Python `importlib.metadata`; install/reinstall/uninstall must preserve
all sibling role bytes and operator files. These fixtures do not prove wheel
installation or execute sibling Ansible tasks. Each sibling repository owns
its role-asset tests; real package installation remains a separate release gate.

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
