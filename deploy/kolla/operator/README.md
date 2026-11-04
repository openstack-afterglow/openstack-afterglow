# Afterglow Kolla Operator Environment

This dependency-only `uv` project supplies the Kolla CLI plus four sibling root
service packages. It does not install an operator application or the
`afterglow-kolla` root deployment-assets distribution. Install that root
distribution explicitly from a reviewed source checkout or wheel into the same
Kolla environment.

## Package ownership

| Distribution | Installed role | Required version |
| --- | --- | --- |
| `drover` | `drover` | `0.2.25` |
| `lumen` | `lumen` | `0.3.1` |
| `waygate` | `waygate` | `0.2.0` |
| `palimpsest-client` | `palimpsest` | `0.3.3` (PyPI) |

Each root wheel owns its role files. The separately installed
`afterglow-kolla` wheel owns the Afterglow role, aggregate playbook and helpers
under `<environment-prefix>/share/afterglow/kolla`. The installer creates stable
Kolla links to those private assets; it does not install the role contents into
Kolla's stable link paths. Sibling roles use their root service distributions,
not separate sibling `*-kolla` packages. Installing a package does not make its
role a Kolla default dependency. The aggregate playbook dispatches enabled
plugin roles only after the installer registers its additive stock `site.yml` import.

The operator manifest and `afterglow-kolla` deployment-assets package require Python 3.11+.

**Current promotion boundary:** the table and checked-in lock retain the
existing sibling pins. This packaging change does not promote them, update
Kolla's pinned commit, synchronize a production venv, or deploy any service.

## Source declaration and release-tag promotion

`pyproject.toml` names the root distributions without `subdirectory` entries.
Palimpsest uses exact `palimpsest-client==0.3.3` from PyPI, with distribution
hashes in `uv.lock` and no Palimpsest Git source. GitHub access to Palimpsest is
not required by normal role installation. Kolla-Ansible remains independently
pinned to `34daacfbf2d5987f543787f57535b2bebe7dee19`. The other promoted root
packages use immutable Git tags and resolved commits; every controller installs
the reviewed lock with `uv sync --locked`.

`afterglow-kolla` is intentionally absent from this manifest/lock: this is
unpublished source packaging, not a published release or a claim that an
immutable release tag already contains it. Install an explicitly reviewed
source/wheel path as shown below until an appropriate release is published.
The public PyPI name `afterglow` belongs to an unrelated project; never run
`pip install afterglow` or `pip install -U afterglow` (including `uv` equivalents)
to install or update this integration. The directory `share/afterglow/kolla`
retains its existing name regardless of the distribution name.

Root-role Git sources must never use a branch, a bare repository URL, or a
mutable `latest` label. This package/lock policy is distinct from application
image selection: the five services follow their existing published GHCR
`latest` channels through `*_image_tag` (`stable` where published). A sibling
release is promotable only when all of these are true:

1. The sibling has pushed an immutable stable `X.Y.Z` tag (historical `vX.Y.Z` is also accepted).
2. The tag and root distribution metadata have exactly the same `X.Y.Z`
   version.
3. The tag contains the package-owned Kolla role that its root wheel installs.
4. The generated operator PR contains the exact matching `tag = "X.Y.Z"` (or historical prefixed tag) source,
   a refreshed `uv.lock`, and an architecture-review stamp.

`.github/workflows/promote-kolla-role-tags.yml` polls the three Git-sourced
siblings (Drover, Lumen and Waygate) hourly and opens or updates a single
`automation/kolla-role-tags` PR. Palimpsest is excluded: update its exact PyPI
requirement and regenerate the lock only after verifying the published wheel
and packaged role. The Git promoter selects the newest stable tag at or above
the already locked version; it never downgrades or promotes prereleases. Human
review and merge remain the boundary before any operator synchronization.

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
python3 scripts/promote_kolla_role_tags.py --check  # Git-sourced roots only
```

## Updating root source dependencies

Git-sourced service promotion is tag-driven. Run the repository-root promotion
command, review its manifest/lock diff, and merge its PR before synchronizing
an operator. Palimpsest follows its separately reviewed exact PyPI requirement:

```bash
python3 scripts/promote_kolla_role_tags.py --latest
```

For an exceptional recovery that cannot wait for the scheduled workflow, record
the exact release tag—never a branch—and regenerate the lock from this
directory:

```bash
uv add --no-sync --tag X.Y.Z "drover @ git+https://github.com/openstack-afterglow/drover.git"
uv add --no-sync --tag X.Y.Z "lumen @ git+https://github.com/openstack-afterglow/lumen.git"
uv add --no-sync --tag X.Y.Z "waygate @ git+https://github.com/openstack-afterglow/waygate.git"
uv lock --refresh
```

For Palimpsest, change only `palimpsest-client==0.3.3` to the reviewed published
version, keep its `[tool.uv.sources]` entry absent, and run `uv lock` without a
broad upgrade. Replacing an installed Git wheel with the same PyPI version needs
`uv sync --locked --inexact --no-install-project --reinstall-package palimpsest-client`;
a plain sync can only audit the old Git installation. Verify role bytes and
unchanged unrelated dependency versions. Package installation does not deploy
Hub images or change the storage/authentication prerequisites.

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

Add the reviewed immutable Git tag containing `afterglow-kolla` to the same
Python 3.11+ operator project; replace `X.Y.Z` only after that tag exists.

```bash
cd /etc/kolla
uv add --no-sync --tag X.Y.Z \
  "afterglow-kolla @ git+https://github.com/openstack-afterglow/openstack-afterglow.git"
# Review pyproject.toml and uv.lock changes before synchronizing.
UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --locked --inexact --no-install-project
```

For unreleased review, use one of the following local artifacts:

```bash
# Non-editable source installation; use the reviewed checkout's absolute path.
uv pip install --python /etc/kolla/.venv/bin/python \
  --reinstall-package afterglow-kolla /absolute/path/to/afterglow
# Alternatively, install the actual reviewed wheel (replace X.Y.Z).
uv pip install --python /etc/kolla/.venv/bin/python \
  --reinstall-package afterglow-kolla \
  /absolute/path/to/afterglow_kolla-X.Y.Z-py3-none-any.whl
```

Retain `--reinstall-package afterglow-kolla` for reviewed artifact updates,
including same-version wheels: it forces reinstallation and package cache refresh.

The same wheel can be installed with `pip` in the selected environment:

```bash
/etc/kolla/.venv/bin/python -m pip install --force-reinstall --no-deps \
  /absolute/path/to/afterglow_kolla-X.Y.Z-py3-none-any.whl
```

**Migration if `openstack-afterglow` is installed:** uninstall that retired
distribution **before** installing `afterglow-kolla` in the same environment:

```bash
uv pip uninstall --python /etc/kolla/.venv/bin/python openstack-afterglow
# Then install the reviewed afterglow-kolla artifact above.
# pip alternative: /etc/kolla/.venv/bin/python -m pip uninstall openstack-afterglow
```

The two names own the same private files; co-installation is unsafe because a
later uninstall of the old distribution can remove the new package's assets.
If both already exist, uninstall the old name and then reinstall
`afterglow-kolla` from the reviewed artifact before registering links or running
Kolla. The installer refuses remaining retired distribution metadata. Stable
links may temporarily dangle during migration. Do not delete source checkouts,
operator configuration or unrelated assets; a checkout link is not proof that
the retired distribution is installed. This documents a conditional migration,
not an observed production installation or rollout.

Prepare `/etc/kolla/config/afterglow/globals.yml` and `secrets.yml`, preserving
existing values, then register the installed assets:

```bash
AFTERGLOW_OPERATOR_LOCK=/absolute/path/to/the/synced/operator/uv.lock \
KOLLA_ANSIBLE_BIN=/etc/kolla/.venv/bin/kolla-ansible \
KOLLA_ANSIBLE_DIR=/etc/kolla/.venv/share/kolla-ansible \
bash /etc/kolla/.venv/share/afterglow/kolla/install.sh
```

The installer validates private asset ownership using the active interpreter's
`afterglow-kolla` distribution metadata. It also verifies that each sibling
role is a real package-owned directory and its distribution version matches the
selected operator lock. Set `AFTERGLOW_OPERATOR_LOCK` to the exact reviewed lock
used to sync the environment; the bundled snapshot is not selected automatically.
The stable links are:

- `<kolla-share>/ansible/roles/afterglow` ->
  `<environment-prefix>/share/afterglow/kolla/ansible/roles/afterglow`
- `<kolla-share>/ansible/afterglow-site.yml` ->
  `<environment-prefix>/share/afterglow/kolla/site.yml`

Wheel installation never writes through those Kolla links into an old checkout.
The installer never replaces sibling role directories or foreign Afterglow
paths. Both Afterglow links are preflighted before either is changed.

For a known legacy Afterglow checkout, set
`AFTERGLOW_REPO_DIR=/absolute/path/to/the/legacy/afterglow` on the installer
command. Only complete link text equal to
`$AFTERGLOW_REPO_DIR/deploy/kolla/ansible/roles/afterglow` or
`$AFTERGLOW_REPO_DIR/deploy/kolla/site.yml`, respectively,
authorizes migration to the installed private assets. An unrelated link,
real directory or file is refused. Invoking `deploy/kolla/install.sh` from a
checkout defaults the legacy path to that checkout; the installed script needs
the explicit variable for a legacy migration. This variable identifies the old
links, not a source of new role bytes. Existing exact package links are retained;
old checkout files are untouched. Retired sibling checkout links require the
separate exact-match procedure in [the deployment guide](../README.md#1-legacy-symlink-migration).

If the role and aggregate playbook point to different old checkouts, identify
the two complete absolute link texts independently:

```bash
AFTERGLOW_LEGACY_ROLE_TARGET=/absolute/old-role-checkout/deploy/kolla/ansible/roles/afterglow \
AFTERGLOW_LEGACY_SITE_TARGET=/absolute/old-site-checkout/deploy/kolla/site.yml \
AFTERGLOW_OPERATOR_LOCK=/absolute/path/to/the/synced/operator/uv.lock \
KOLLA_ANSIBLE_BIN=/etc/kolla/.venv/bin/kolla-ansible \
KOLLA_ANSIBLE_DIR=/etc/kolla/.venv/share/kolla-ansible \
bash /etc/kolla/.venv/share/afterglow/kolla/install.sh
```

Each explicit target overrides only its corresponding `AFTERGLOW_REPO_DIR`
fallback. It authorizes an exact existing link text, not a new source or a
guessed path. Inspect both links before selecting these values. Both link
destinations are preflighted before changes, and the source checkouts remain
untouched.

Installation and registration alone are not production deployment, image
publication, operator-lock promotion, service restart or live acceptance.

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
Kolla commit and deployed image digests, review exact root-role package pins
(PyPI version/hashes for Palimpsest; immutable tags for the other roots), snapshot
the venv/configuration, and verify a locked/inexact dry-run before syncing.
Pass the actual synchronized lock using `AFTERGLOW_OPERATOR_LOCK`; do not
substitute the potentially older package snapshot.
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
requirement, unmanaged Lumen sandbox images, root-role package pins, human
promotion, or the deployment guide's reviewed schema migration requirements.

See [the deployment guide](../README.md) for inventory, configuration, legacy
symlink migration, and uninstall ownership details.
