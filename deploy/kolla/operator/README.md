# Afterglow Kolla Operator Environment

This dependency-only `uv` project supplies the Kolla CLI plus the root service
packages that own the Afterglow plugin roles. It does not install an operator
application.

## Package ownership

| Distribution | Installed role | Required version |
| --- | --- | --- |
| `drover` | `drover` | `0.2.24` |
| `lumen` | `lumen` | `0.3.0` |
| `waygate` | `waygate` | `0.1.4` |
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

From `/etc/kolla`, use the ordinary Kolla command line:

```bash
kolla-ansible deploy -i multinode
kolla-ansible reconfigure -i multinode --tags afterglow,waygate,drover,lumen,palimpsest
```

See [the deployment guide](../README.md) for inventory, configuration, legacy
symlink migration, and uninstall ownership details.
