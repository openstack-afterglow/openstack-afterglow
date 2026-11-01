## Why

The unchanged direct development Compose invocation builds successfully but its four migration/bootstrap jobs fail because the selected shared MariaDB node (controller1) disconnected from an existing healthy two-node Primary. Read-only inspection also found an obsolete local Lumen0.6.9 build pin incompatible with the deployed0.6.12 credential-key schema, plus the current Afterglow image requires SQL103's missing nullable column.

## What Changes

- Preserve original DB destinations, credentials, encryption/signing keys, ports, volumes, source snapshots and unrelated services.
- Under explicit approval, preserve controller1's configuration/cold datadir and normally restart only its native MariaDB service to rejoin the existing Primary. Never create a new Primary or disable WSREP.
- Under a second explicit approval, change only LUMEN_BUILD_CONTEXT to an immutable extraction of deployed Lumen0.6.12 revision9d94d0b51f2dcee9d47fdb05004de4c7558fa661. All other environment values remain unchanged.
- Qualify SQL103 against a protected snapshot restored into MariaDB10.11.19. The latest user decision explicitly declines key alignment and production app changes, so do not apply live SQL103 or drain/restart production applications.
- Preserve the full-startup blocker rather than run incompatible writers: local Afterglow/Waygate/Drover master keys differ from production and the required SQL103 column is absent. Authenticated application acceptance is not claimed.

## Capabilities

### New Capabilities

None. This is an operational recovery and source-pin correction, not a feature or new deployment path.

### Modified Capabilities

The original database paths are restored and the Lumen source-build pin matches deployed0.6.12. Full application startup remains blocked by the latest user decision; this is not deployment acceptance.

## Impact

Production DB node1 normal rejoin was explicitly approved; nodes2/3 remain running. SQL103 affects shared afterglow_kolla and therefore requires backup/restore, schema comparison and approved writer coordination. Existing application production versions, native identities, grants and infrastructure are not upgraded by this change. Evidence is private under ~/.local/share/afterglow-proofs/unchanged-env-recovery-20261030/. No commits or pushes.
