## Why

The standard full-inventory Kolla reconfigure must select current published application images and prepare authenticated Cloud Shell checks on a fresh toolbox, rather than relying on prior tagged invocations or stale operator pins.

## What Changes

- Prepare the shared toolbox cloud configuration before Cloud Shell and Manila checks; retain the Manila plugin installation only when Manila is enabled.
- Preserve per-invocation immutable image resolution and operator-selected datastore pins; configure the deployment to follow published application channels.
- Verify the full untagged Kolla command and its actual resulting services, without altering migration or credential safeguards.

## Capabilities

### New Capabilities
- `kolla-standard-reconfigure`: Standard Kolla reconfiguration prepares independent authenticated checks and selects published application images safely.

### Modified Capabilities

None.

## Impact

Afterglow Kolla roles and their contract verification; operator image selection and deployment acceptance. Lumen 028 is a separate data migration and requires its own verified recovery and compatibility evidence.
