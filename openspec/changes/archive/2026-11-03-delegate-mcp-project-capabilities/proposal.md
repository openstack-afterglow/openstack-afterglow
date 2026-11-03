## Why
All-project management consent currently rejects the entire grant when any membership is read-only. Users need an accurate, least-privilege mixed-project delegation and an explicit preview of independent native service capabilities.

## What Changes
- Accept all-project management consent with per-project read/write ceilings; reader projects remain read-only.
- Resolve Drover, Palimpsest, Waygate and Lumen authority independently through existing native service policies, never generic project-role escalation.
- Show project-specific effective cloud and service permissions before consent; unknown policy is not permission.
- Preserve restricted credentials, live authorization, read attenuation, scope isolation and no-replay mutation lifecycle.

## Capabilities
### New Capabilities
- `mcp-project-capability-consent`: Mixed-project delegation and native service capability previews and enforcement.
### Modified Capabilities

## Impact
Backend MCP authority and project discovery API, service policy integration, OAuth consent and nine locales, regression coverage and existing documentation. No production rollout, credential/grant mutation or schema change is authorized by this implementation.
