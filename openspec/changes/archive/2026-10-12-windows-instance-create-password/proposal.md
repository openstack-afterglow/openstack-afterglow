## Why

The WireGuard host (`wireguard-dmslab`, verified hostname `wireguardserver`) Windows README and `cloud/initial-password-userdata.example.ps1` describe a verified first-boot password path for the existing Cloudbase image. Its `inject_user_password=false` means Nova `adminPass` alone does not set the requested guest password. Afterglow already accepts `admin_pass` in the backend but exposes only SSH access in its VM wizard.

## What Changes

- Expose the non-secret `windows_initial_password_method` and `os_admin_user` image fields. Offer password+confirmation for a boot image or volume with `os_type=windows`, `windows_initial_password_method=cloudbase-user-data` and a known `os_admin_user`; do not hardcode a UUID, account, host, network or security group.
- Resolve the actual selected Glance image or Cinder boot-volume metadata in the request's project connection. Generate the verified `#ps1_sysnative` / `ConvertTo-SecureString` / `Set-LocalUser` script with safely quoted password/account and require config drive on synchronous, user SSE and administrator SSE creation.
- Use the existing `admin_pass` API field as a secret. Do not expose it in validation failures, upstream errors, logs, audit/history, metadata, the review screen or browser persistence. Clear password drafts on boot/target/actor change, close/reset and submission.
- Windows password provisioning is not Linux cloud-init: reject incompatible custom user-data, GitHub SSH or data mounts before mutation instead of silently discarding them. GPU flavors remain allowed with normal GPU quota/capacity admission, but the Windows password path must not generate Linux GPU bootstrap. Existing non-password and non-Windows Nova `adminPass` behavior remains unchanged.
- Keep RDP firewall configuration explicit. Explain that ACTIVE/API completion does not prove first-boot completion or RDP login. No production mutation, new VM, IAM, image alteration, deployment, commit or push is authorized by this feature request.

## Capabilities

### New Capabilities

- Image-aware Windows first-boot password deployment from the existing instance wizard and all create APIs.

### Modified Capabilities

- VM create access readiness, review and progress now include supported Windows password access without a required SSH key.

## Impact

Backend request secret handling, image metadata projection, create preflight and user-data generation; frontend wizard state/config/review and four locale catalogs; focused regression tests and existing instance docs. No schema, database migration, external dependency, production configuration or service topology change. Local HTTP/native-SDK and synthetic browser evidence are separate from the existing remote Windows guest proof; a new live VM/RDP run is not claimed.
