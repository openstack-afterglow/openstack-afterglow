## Why
The user requested project-specific permissions wherever access is granted, but personal-key issuance still lacks the OAuth preview. Eager serial policy evaluation on the shared project-list endpoint can also block otherwise valid read-only grant flows when a service is slow.

## What Changes
- Reuse one permission preview for OAuth and personal-key issuance.
- Restore cheap project discovery by default and make enriched preview explicit with `preview=true`.
- Bound independent project workers and native-policy call deadlines; preserve individual unknown rows/service states instead of aborting every project.
- Preserve reader/write ceilings, service-policy fail-closed runtime, read attenuation, owner fences and no production mutations.

## Capabilities
### New Capabilities
### Modified Capabilities
- `mcp-project-capability-consent`: Cover both grant forms and isolate unavailable preview authority from membership discovery.

## Impact
Backend MCP preview endpoint/evaluator; account and OAuth frontend grant forms/shared preview; focused behavior tests and existing docs. No native role/schema/deployment changes. Real Drover/Waygate restricted-token native policy interoperability remains separately unqualified.
