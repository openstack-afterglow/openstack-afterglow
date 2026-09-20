# Afterglow Kolla Operator Environment

This dependency-only `uv` project supplies the Kolla CLI plus the root service
packages that own the Afterglow plugin roles. It does not install an operator
application.

## Package ownership

| Distribution | Installed role | Required version |
| --- | --- | --- |
| `drover` | `drover` | `0.2.22` |
| `lumen` | `lumen` | `0.2.2` |
| `waygate` | `waygate` | `0.1.3` |
| `palimpsest-local` | `palimpsest` | `0.1.4` |

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
installs with `uv sync --frozen`.

The operator must never consume a branch, a bare repository URL, or a mutable
`latest` label. A sibling release is promotable only when all of these are
true:

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

Until the current root-package versions are tagged, their existing full commit
pins remain valid and intentionally stay unchanged. Do not invent or move a
tag just to change this representation.

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
uv add --no-sync "drover @ git+https://github.com/openstack-afterglow/drover.git@vX.Y.Z"
uv add --no-sync "lumen @ git+https://github.com/openstack-afterglow/lumen.git@vX.Y.Z"
uv add --no-sync "waygate @ git+https://github.com/openstack-afterglow/waygate.git@vX.Y.Z"
uv add --no-sync "palimpsest-local @ git+https://github.com/openstack-afterglow/palimpsest.git@vX.Y.Z"
uv lock --refresh
```

After the reviewed manifest and lock are present, install them into the actual
Kolla environment:

```bash
UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --frozen --inexact --no-install-project
source /etc/kolla/.venv/bin/activate
```

`--no-install-project` is required because this operator project is a dependency
manifest, not an application. `--inexact` preserves unrelated packages already
needed by the cloud operator.

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

From `/etc/kolla`, use the ordinary Kolla command line:

```bash
kolla-ansible deploy -i multinode
kolla-ansible reconfigure -i multinode --tags afterglow,waygate,drover,lumen,palimpsest
```

See [the deployment guide](../README.md) for inventory, configuration, legacy
symlink migration, and uninstall ownership details.
