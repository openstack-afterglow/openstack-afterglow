## Why
Local Afterglow runs the base 1.30.26 auth modules, while Kolla already deploys a native OIDC adapter for its authoritative schema-2.0 ephemeral Accounts mapping. Local callbacks reject the intentional live mapping with native_mapping_unsafe. Do not alter Keystone mapping or revert its operator contract.

## What
Port the deployed adapter's verified native identity selection, Personal reuse/recovery, stale accepted intent retirement and password shadow-user filtering into source. Make the native path an explicit TOML/Pydantic per-provider opt-in pinned to complete native mapping ID/canonical SHA-256 and Accounts/Personal domain IDs. Preserve all other provider flows and existing dirty changes. Synchronize config example and K8s generation.

## Verification
Use exact deployed mapping and actual native read-only directory/protocol probes; isolated stateful HTTP callback/session scenarios and changed-boundary regressions; isolated canonical gate. Reject digest drift, foreign Personal authority, stale entry/link and unconfigured provider. Local legacy Default provider remains unsupported unless explicitly configured; do not silently grant trust. No shared mapping/IAM/schema changes, commits or deployment.
