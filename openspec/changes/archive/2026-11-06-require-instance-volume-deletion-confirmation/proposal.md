## Why
Automatic volume deletion needs explicit acknowledgment before deleting an instance.

## What Changes
- Show affected volumes and require a localized deletion word only when automatic deletion is enabled.
- Retain ordinary confirmation otherwise.

## Capabilities
### New Capabilities
- `instance-volume-deletion-confirmation`: localized destructive confirmation.
### Modified Capabilities
None.

## Impact
Shared frontend confirmation primitive, instance controller and nine locale catalogs; no API/schema changes.
