## Context
Consumer MCP creates a single image-backed Nova VM with a Cinder boot volume. Current key and size defaults and absent security-group selection permit unintended defaults. Existing key lookup must never seed ownership into an SDK resource.

## Goals / Non-Goals
**Goals:** Require explicit boot size, user-owned key, flavor, network and project-owned security groups; validate in preview and immediately before dispatch; preserve exact selections in fingerprint and provider request.

**Non-Goals:** Change existing instances, create SSH keys, alter grant permissions, or deploy to production.

## Decisions
Use mandatory typed request fields and a nonempty bounded UUID list for groups. Confirm exact provider ownership for each group and the requesting user key. Pass only validated group identities to the native create operation; never attach and subsequently repair an instance. Continue image, flavor, network, capacity, usage scheduling and idempotency controls.

## Risks / Trade-offs
This is a breaking MCP schema change: existing automated clients must provide explicit values. Provider group identifier handling must be verified against the installed SDK; unknown outcomes must never be resent blindly. Operational rollout is separate.
