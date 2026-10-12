## Why

Operators need a browser workflow to configure an image for Afterglow Windows service without editing many arbitrary properties or confusing an OS label with a working guest. Current shared image details offer only per-key editing. Password creation intentionally supports the native `nova-adminpass-configdrive` method; the earlier `cloudbase-user-data` image must not be relabeled automatically because its guest configuration differs. A previously observed native Windows image also requires min_disk=80 while the wizard's retained/default boot disk can remain20GB, preventing creation before password delivery.

## What Changes

- Add an explicit Windows service setup section to shared user/admin image details using existing owner/admin edit authority and the existing properties PATCH API. No new endpoint or second backend preset convention.
- Apply five core properties in one request: `os_type=windows`, `os_distro=windows`, operator-selected `os_admin_user`, `windows_initial_password_method=nova-adminpass-configdrive`, `img_config_drive=mandatory`.
- Offer opt-in Windows11 x86 UEFI/q35/TPM2.0-CRB/SecureBoot properties (`hw_firmware_type=uefi`, `hw_machine_type=q35`, `hw_tpm_version=2.0`, `hw_tpm_model=tpm-crb`, `os_secure_boot=required`). Offer `hw_qemu_guest_agent=yes` only with explicit installed-agent confirmation. Do not force image-specific SATA/VirtIO/controller/CPU topology or mark unselected features absent.
- Show current configuration and current→proposed changes, preserve unrelated properties/visibility/owner/digests/trust, validate the login account, and require explicit confirmation that the actual guest is prepared for native password injection. The browser cannot install Cloudbase-Init, change inject_user_password, fix drivers, seal Windows, configure hypervisor TPM or certify guest/RDP readiness. Legacy/unknown methods are not silently upgraded. Applying flags never approves verification or production readiness.
- Save with busy/error handling and request identity/generation fences; preserve draft on retryable errors and discard cross-image/actor/project/mode stale results. Existing arbitrary-properties editing remains available without losing its draft.
- Correct the demonstrated existing properties-save catalog invalidation boundary: both user/admin property mutations invalidate all project Glance image-list caches so warm owner/shared catalogs and subsequent VM wizard loads consume the saved method/account. Two real cached HTTP regressions failed before this correction and passed after it; no new API surface.
- Correct demonstrated native SDK defects in the existing properties adapter: version-relative `/images/{id}` (not duplicated `/v2`), explicit provider-error raising instead of false success, and detail projection of normalized ConfigDrive/machine-type/SecureBoot/QGA fields. The strict installed-SDK HTTP smoke first failed on unchanged properties, then missing ConfigDrive readback; both were corrected without weakening the provider fixture. Keep native HTTP persistence/error consumer regressions.
- Enforce the selected image's authoritative minimum boot disk in shared wizard selection/retained metadata, input and Next/deploy readiness. Raise undersized initial drafts without shrinking larger drafts; existing-volume reuse is independent. The real Cinder smoke fixture rejects undersized requests rather than inventing a larger successful volume.
- Localize operator guidance in ko/en/ja/zh-CN, document required image/guest/cloud prerequisites, and verify browser save→native Glance JSON-Patch→reread, reload persistence, authorization/error/stale boundaries and VM create minimum delivery.

## Capabilities

### New Capabilities

Browser-based Windows image service property preset with preview and explicit guest-preparation confirmation.

### Modified Capabilities

Shared image detail metadata updates and shared VM wizard minimum boot-volume admission.

## Impact

Frontend/controller/locale and current docs/tests only unless an existing API defect is demonstrated. Existing image properties API/SDK adapter is reused. No DB/schema/dependency/auth expansion, production image/binary/VM/SG mutation, image sharing, trust approval, guest setup, deployment, commit or push. Work stays on dev and preserves concurrent changes and shared index/private config. Local synthetic cloud and prior operator/live evidence remain distinct.
