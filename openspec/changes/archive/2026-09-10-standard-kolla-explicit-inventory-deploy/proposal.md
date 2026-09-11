# Standard Afterglow and Lumen Kolla deployment

## Why
Operators should be able to run `kolla-ansible deploy -i multinode` from `/etc/kolla` after the one-time plugin installation. The controller 3 recovery reproduced a missing privilege-escalation declaration: toolbox Docker access failed unless the operator supplied `--become`. The local installer also pins lumen-kolla 0.1.8 whereas the verified published/runtime package is 0.2.0.

## What Changes
- Declare privilege escalation at the custom service and HAProxy play boundary, covering nested/delegated tasks without requiring global Ansible configuration or a replacement Kolla CLI.
- Keep the stock site import, explicit/default inventory, globals.d loading, immutable runtime images and package-owned Lumen role.
- Align the installer/operator lock with the verified published lumen-kolla 0.2.0 wheel.
- Document one-time environment/bootstrap requirements and the exact ordinary deploy command; preserve operator-owned credentials and existing overrides.
- Add offline structural contracts and real Ansible/Kolla CLI fixture execution without command-line privilege/tag workarounds, plus a failure control.

## Constraints and completion
Use dev, preserve unrelated dirty source and deployed overrides, and retain secret isolation. Changes to installed integration require reviewed, tested source. Do not run unrelated OpenStack lifecycle actions merely to test custom service integration. Verify plain CLI dispatch in the isolated runtime fixture and service-tagged live execution without --become, explicitly reporting the difference. Complete required checks, independent review and architecture maintenance before closure.
