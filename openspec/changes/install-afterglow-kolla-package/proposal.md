## Why

Afterglow's Kolla role and aggregate playbook are linked to a source checkout, unlike the installed sibling packages. Installing or upgrading Afterglow must update its Kolla assets without silently modifying a checkout or operator state.

## What Changes

- Provide an installable `afterglow-kolla` root distribution carrying Kolla assets and integration tools under the unchanged `share/afterglow/kolla` path.
- Switch Kolla integration to package-owned assets with a safe, explicit migration from legacy source links, including independently identified role and aggregate-playbook checkout targets.
- Require removal of an installed retired `openstack-afterglow` distribution before installing/reinstalling `afterglow-kolla`, because both own the same private assets; refuse leftover legacy metadata without automatic removal.
- Validate real wheel installation, update, standard Kolla discovery and ownership boundaries without changing production.
- Document explicit pip/uv source or wheel installation without assuming a published package or release tag; preserve the separate operator lock and production authorization boundary.

## Capabilities

### New Capabilities
- `afterglow-kolla-package`: Versioned installation and upgrade of Afterglow Kolla assets.

### Modified Capabilities

None.
