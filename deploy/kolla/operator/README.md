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

The controller and every root package require Python 3.12 or newer.

## Source declaration and current pin status

`pyproject.toml` names the root distributions and pins each Git source to a
full immutable commit SHA, without `subdirectory` entries. `uv.lock` resolves
those commits to the versions in the ownership table above. Kolla-Ansible
remains independently pinned to `34daacfbf2d5987f543787f57535b2bebe7dee19`.

Use the committed lock for installation. Updating a service requires a tested
root-package commit, an updated source pin, and a regenerated/reviewed lock;
do not infer package versions from Git tag names.

## Updating root source dependencies

From this directory, record root-package sources without creating or changing a
local environment during each `uv add`:

```bash
uv add --no-sync "kolla-ansible @ git+https://opendev.org/openstack/kolla-ansible.git@34daacfbf2d5987f543787f57535b2bebe7dee19"
uv add --no-sync "drover @ git+https://github.com/openstack-afterglow/drover.git@<drover-root-commit>"
uv add --no-sync "lumen @ git+https://github.com/openstack-afterglow/lumen.git@<lumen-root-commit>"
uv add --no-sync "waygate @ git+https://github.com/openstack-afterglow/waygate.git@<waygate-root-commit>"
uv add --no-sync "palimpsest-local @ git+https://github.com/openstack-afterglow/palimpsest.git@<palimpsest-root-commit>"
```

After reviewing the resulting manifest and lock, install into the actual Kolla
environment:

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
