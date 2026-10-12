## Why

The operator verified Windows image `aaf955e8-62b4-402a-b219-ffd269b38cae` with the actual OpenStack CLI `--password` plus ConfigDrive and subsequent native/RDP desktop login. A read-only live image lookup confirms `os_type=windows`, `os_admin_user=Admin`, `windows_initial_password_method=nova-adminpass-configdrive`, `img_config_drive=mandatory`, private visibility and `production_ready=false`. The retained report `/etc/kolla/reports/windows11-native-password-20261012/verified-summary.json` records guest ConfigDrive password equality, no user-data/keypair/password-reset, RDP authentication and desktop success. Afterglow currently admits only `cloudbase-user-data`, suppresses Windows Nova `adminPass`, and generates a PowerShell password-reset script. It therefore cannot use the verified native image correctly.

## What Changes

- Cut over supported Windows creation to the exact provider marker `nova-adminpass-configdrive`; pass the unchanged secret as Nova `adminPass` with `config_drive=true` and no generated user-data. Remove the obsolete password PowerShell generator and migrate all callers/regressions.
- Preserve project-scoped authoritative image/boot-volume metadata, volume ownership, secret validation/redaction/lifecycle, admission/rollback, no Linux GPU bootstrap, and explicit incompatible userdata/GitHub/Manila rejection.
- Recognize the native marker in the shared user/admin wizard. Metadata-confirmed unsupported Windows must display an actionable unsupported-image message and must not silently become SSH access. No fixed image/account/host is embedded in application logic.
- Update four-locale UI/public guides and current API/operator docs to describe native Nova/ConfigDrive delivery, first-boot waiting and explicit RDP security-group setup.
- Reproduce the admission discrepancy locally, then verify real FastAPI/installed SDK native HTTP serialization and actual compiled browser interaction. Keep synthetic identity/cloud boundaries separate from the operator's earlier live guest evidence.

## Capabilities

### New Capabilities

None; correct the existing Windows initial-password feature.

### Modified Capabilities

Windows image/volume admission and initial-password delivery across user sync/SSE and administrator SSE creation; shared wizard access readiness and unsupported-source handling.

## Impact

No DB/schema/migration/dependency/auth/service-topology change. No production deployment, VM creation/reset, image sharing/property mutation, infrastructure changes, commit or push. Preserve concurrent working-tree/index changes and original cloud resources. Read-only runtime/image/report inspection is allowed; new runtime proof uses disposable local fixtures only.
