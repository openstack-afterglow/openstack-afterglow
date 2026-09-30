## Why

The API-key settings screenshots present Codex and Claude Code snippets, but masked API-key prefixes and model-ID placeholders cannot be executed as-is. The documented Codex command also omits a certificate trust precondition observed with the installed macOS CLI. The actual remote Claude Code path must be exercised rather than inferred from SDK compatibility.

## What Changes

- Verify both clients against the deployed Lumen API with an authorized ordinary key and real model IDs, including a local-tool continuation where supported.
- Clarify which key, model, base URL, and client-specific setup users must supply; never place key values in copied instructions.
- Keep an existing Codex desktop-app provider unchanged when explaining an optional terminal-only Lumen profile; do not present one Mac's CA path as a universal requirement.
- Align the API-key UI, consumer documentation, architecture evidence, and changelog with what was actually observed.

## Capabilities

### Modified Capabilities

- `chat-api-key-management`: connection guide states executable prerequisites and boundaries for Codex and Claude Code.

## Impact

Only client guidance and supporting UI/documentation are in scope. API-key issuance, backend routing, provider credentials, deployed Lumen, and the user's existing application login are unchanged.
