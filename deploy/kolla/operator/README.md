# Afterglow Kolla Operator Environment

This dependency-only `uv` project supplies the Kolla CLI plus the root service
packages that own the Afterglow plugin roles. It does not install an operator
application.

## Package ownership

| Distribution | Installed role | Required version |
| --- | --- | --- |
| `drover` | `drover` | `0.2.25` |
| `lumen` | `lumen` | `0.3.1` |
| `waygate` | `waygate` | `0.2.0` |
| `palimpsest-client` | `palimpsest` | `0.2.3` |

Each root wheel owns its role files. No separate `*-kolla` distribution is
installed, and installing one of these packages does not make its role a Kolla
default dependency. The Afterglow aggregate playbook dispatches only enabled
plugin roles after `../install.sh` has registered its stock-site import.

The controller and every root package require Python 3.11 or newer.

## Source declaration and release-tag promotion

`pyproject.toml` names the root distributions without `subdirectory` entries.
Kolla-Ansible remains independently pinned to
`34daacfbf2d5987f543787f57535b2bebe7dee19`. A promoted root package uses an
explicit immutable Git `tag = "vX.Y.Z"`; `uv.lock` then records that tag's
resolved commit. The lock—not a floating Git ref—is what every controller
installs with `uv sync --locked`.

Root-role Git sources must never use a branch, a bare repository URL, or a
mutable `latest` label. This package/lock policy is distinct from application
image selection: the five services follow their existing published GHCR
`latest` channels through `*_image_tag` (`stable` where published). A sibling
release is promotable only when all of these are true:

1. The sibling has pushed an immutable stable `vX.Y.Z` tag.
2. The tag and root distribution metadata have exactly the same `X.Y.Z`
   version.
3. The tag contains the package-owned Kolla role that its root wheel installs.
4. The generated operator PR contains the matching `tag = "vX.Y.Z"` source,
   a refreshed `uv.lock`, and an architecture-review stamp.

`.github/workflows/promote-kolla-role-tags.yml` polls the four sibling tag
sets hourly and opens or updates a single `automation/kolla-role-tags` PR. It
selects only the newest stable tag at or above the already locked version, so
it never downgrades an operator or promotes a prerelease. The PR is a required
human review boundary; merging it is what permits the tag to reach a Kolla
environment. Trigger the workflow manually after a release when an immediate
promotion is needed.

The workflow opens and updates the PR with `GITHUB_TOKEN`, so GitHub starts no
`pull_request` checks on it, including after its hourly force-push. While the
promotion is unmerged, every hourly run force-pushes a new commit built from
`main`. Before merging, close and reopen the PR so that `Layered Tests (PR)`
runs, then confirm that the PR head is still the commit those checks ran on;
if it is not, close and reopen it again. Do not dispatch
`docker-build.yml` on `automation/kolla-role-tags`: a dispatch builds and
pushes `dev`-family images from that branch.

To inspect or manually generate the same reviewed update from the repository
root:

```bash
python3 scripts/promote_kolla_role_tags.py --latest
python3 scripts/promote_kolla_role_tags.py --check  # after all roots use tags
```

## Updating root source dependencies

Normal service promotion is tag-driven. Run the repository-root promotion
command, review its manifest/lock diff, and merge its PR before synchronizing
an operator:

```bash
python3 scripts/promote_kolla_role_tags.py --latest
```

For an exceptional recovery that cannot wait for the scheduled workflow, record
the exact release tag—never a branch—and regenerate the lock from this
directory:

```bash
uv add --no-sync --tag vX.Y.Z "drover @ git+https://github.com/openstack-afterglow/drover.git"
uv add --no-sync --tag vX.Y.Z "lumen @ git+https://github.com/openstack-afterglow/lumen.git"
uv add --no-sync --tag vX.Y.Z "waygate @ git+https://github.com/openstack-afterglow/waygate.git"
uv add --no-sync --tag vX.Y.Z "palimpsest-client @ git+https://github.com/openstack-afterglow/palimpsest.git"
uv lock --refresh
```

### Security floor updates

Updating dependency security floors (such as setting an explicit floor like
`urllib3>=2.8.0` in `pyproject.toml` and locking only that package with
`uv lock --upgrade-package <pkg>`) is distinct from root service role promotion
and production environment sync. A security floor update preserves every service
Git ref, release tag, and commit pin unchanged, without triggering role tag
promotion workflows or synchronizing directly into a live `/etc/kolla` runtime.
Production synchronization remains a separate, explicitly reviewed operator step.

After the reviewed manifest and lock are present, install them into the actual
Kolla environment:

```bash
UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --locked --inexact --no-install-project
source /etc/kolla/.venv/bin/activate
```

`--no-install-project` is required because this operator project is a dependency
manifest, not an application. `--inexact` preserves unrelated packages already
needed by the cloud operator.

Palimpsest 0.2.3 renamed its root distribution from `palimpsest-local` to
`palimpsest-client`; both install the same `palimpsest` role files. Because
`--inexact` never removes the retired distribution, migrate an existing Kolla
environment explicitly before running `../install.sh`:

```bash
uv pip uninstall --python /etc/kolla/.venv/bin/python palimpsest-local
UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --locked --inexact --no-install-project --reinstall-package palimpsest-client
```

The installer refuses to continue while `palimpsest-local` metadata remains.

## Install and lifecycle

After the root packages have been synchronized, prepare
`/etc/kolla/config/afterglow/globals.yml` and `secrets.yml`, then run:

```bash
KOLLA_ANSIBLE_BIN=/etc/kolla/.venv/bin/kolla-ansible \
KOLLA_ANSIBLE_DIR=/etc/kolla/.venv/share/kolla-ansible \
../install.sh
```

The installer verifies that each role is a real package-owned directory and
that the active environment reports the distribution/version in the table
above. It creates only the Afterglow role and aggregate-playbook links; it
never links, replaces, or removes root-package role directories.

After any Kolla package reinstall, rerun the installer: the package can replace
stock `site.yml` and remove its additive Afterglow import even while all role and
aggregate-playbook links remain valid. Verify the actual canonical path before
restarting services:

```bash
cd /etc/kolla
kolla-ansible reconfigure -i multinode \
  --tags afterglow,waygate,drover,lumen,palimpsest --list-tasks
```

The output must include all five enabled custom service plays. A zero exit code
with only stock plays is not integration proof. `--list-tasks` verifies dispatch,
not authenticated configuration, migrations, service restart or cluster health.
`genconfig` writes controller configuration and is not a dry run. Even a plugin
tagged reconfigure invokes native loadbalancer config/check tasks; enabled
HAProxy, ProxySQL and Keepalived handlers can restart changed services.

For explicitly authorized current-state recovery, preserve the actual installed
Kolla commit and deployed image digests, review immutable root-role tags against
those images, snapshot the venv/configuration, and verify a locked/inexact dry-run
before syncing. If that operator has its own reviewed manifest/lock, pass
`AFTERGLOW_OPERATOR_LOCK=/etc/kolla/uv.lock` to the existing installer rather than
changing this repository's release-promotion pins or using a custom playbook.
Keep fresh operator authentication, restorable datastore backups and full-stock
storage/availability gates separate from operator-path preparation.

A recovery gate requires an explicit census and quiescence evidence for every
old writer (including controllers and separately deployed batch workers), not
only named API and worker containers. Validate the matching logical dumps by
actually importing them into isolated, disposable instances with the source
database major/version, no production network, credentials, sockets or mounts,
and comparing schema/data counts. `gzip -t` and `pg_restore --list` establish
archive integrity only. MariaDB `--databases` dumps contain `CREATE DATABASE`
and `USE`; do not import them into a different scratch schema on production.
Recovery also needs matching keys, policy/configuration and plugin/image
material; a file-presence receipt alone does not establish those dependencies.

The 2026-10-06 Afterglow1.30.2/Lumen0.6.3 cutover records six API/worker stops,
not a complete writer census or a pre-cutover import receipt. Later isolated
restoration and current readiness cannot prove historical writer quiescence
or repair a skipped precheck. Keep these gaps explicit in
`openspec/changes/release-ecosystem-20261002/tasks.md`; do not mark the full
deployment gate complete or restart a newer concurrent rollout to match an
older session's expected image pins.

The historical stopped-dump rehearsal on 2026-10-07 passed actual imports into
network-none, tmpfs-only MariaDB10.11.19 and PostgreSQL16.14 instances: 58 SQL
tables/5,101 rows (21 migration records) and 4 PostgreSQL tables/1,938 rows
matched the dump, with both owned containers removed. This is post-cutover
logical-restoration evidence only, not proof of pre-cutover quiescence or a
full recovery with matching keys, configuration and plugins.

From `/etc/kolla`, use the ordinary Kolla command line:

```bash
kolla-ansible deploy -i multinode
kolla-ansible reconfigure -i multinode --tags afterglow,waygate,drover,lumen,palimpsest
```
The exact native spelling `--tag afterglow,lumen,drover,palimpsest,waygat`
also selects all five services; no wrapper or input correction is required.
The Waygate play explicitly inherits both `waygate` and `waygat` tags through
image preparation and role execution, and its HAProxy configuration/reconcile
path accepts either tag. CLI service selection does not change image versions:
explicit `*_image_ref` digest pins and installed root-package versions remain
effective until separately authorized release promotion.


For enabled published-image services, `prechecks`, `pull`, `deploy`,
`reconfigure`, and `upgrade` resolve moving image tags on the first targeted
controller for each service. The registry digest selection is shared across
all targeted serial batches and is refreshed on the next invocation. `pull`
downloads images only; `deploy`, `reconfigure`, and `upgrade` replace containers
when their selected images change. Source-build and disabled components skip
lookup; service tags and `--limit` determine which services/controllers
participate. Explicit component `*_image_ref` version/digest pins skip lookup
and remain the controlled release/rollback path.

Component enablement may differ by controller. Selection covers only components
enabled on enabled published-mode service consumers before any serial consumer
starts; disabled and source-mode hosts do not contribute. Each controller receives
only locally enabled references. Effective host image/ref and service namespace/tag
inputs preserve later-only worker rollback pins. Contradictory effective inputs for
one component fail before registry or credential access; reconcile them or split
targets with `--limit`. Three Palimpsest APIs and one worker share one frozen selection.

Selection readiness must belong to the current service, not an earlier service.
If its first target is disabled or in source mode, later published-image targets
cannot reuse earlier facts; use separate homogeneous invocations with `--limit`.

Native Kolla globals and `-e` extra-vars take precedence over selected facts;
an effective mutable `*_image_ref` override is rejected rather than dispatched.
Remove old mutable or bare `*_image_ref` entries from globals and extra-vars,
and use the service `*_image_tag` instead (for example,
`-e afterglow_image_tag=latest`). Immutable `*_image_ref` pins remain supported.
This does not change stock images, datastore pins, Cloud Shell's digest
requirement, unmanaged Lumen sandbox images, root-role Git pins, human package
promotion, or the deployment guide's reviewed schema migration requirements.

See [the deployment guide](../README.md) for inventory, configuration, legacy
symlink migration, and uninstall ownership details.
