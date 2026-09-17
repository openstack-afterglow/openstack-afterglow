## Why
Operators should install each sibling service directly from its Git repository root without selecting deploy/kolla. Keep service and deployment dependencies isolated: extras add dependencies, so Kolla/Ansible must not be a base dependency inherited by service images.

## What Changes
- Root service distributions ship their existing Kolla role shared-data; retire standalone *-kolla distribution metadata and markers.
- Runtime dependencies become explicit service extras; preserve independent SDK/Hub contracts where required by existing callers.
- Move container build assets beneath docker/ while preserving repository-root build context and update every consumer.
- Update Afterglow operator distribution names, immutable Git references, ownership checks, CLI instructions, and upgrade procedure.

## Scope and Constraints
Drover, Lumen, Waygate, Palimpsest dev and Afterglow dev. Palimpsest implementation is isolated in /tmp/palimpsest-root-package; the user's divergent feature checkout remains untouched. Do not copy its architecture/handoff files into dev. Existing tags are immutable; do not relabel old releases as unified root packages. No production deployment or registry permission change.

## Completion Criteria
Build real root wheels and assert installed role data, empty/shared base dependencies and absence of Kolla/Ansible from service resolution. Exercise documented uv add, pip install, uv pip install and operator install/uninstall with real packages. Run relevant sibling tests and Afterglow test:gate. Update current architecture/docs from source and archive only after evidence is complete.
