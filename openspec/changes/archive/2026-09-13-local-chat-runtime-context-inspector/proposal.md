## Why

The settings page exceeds a large viewport because navigation and component sizing have separate height ownership. Live screenshots still show unavailable context and a failed tool-selection call presented as completed, so synthetic UI tests alone did not establish deployed Perplexity behavior. Developers need a root-repository local stack that builds the current sibling services and supports real API/worker verification.

## What Changes

- Give settings return navigation, heading and body one responsive height/scroll contract.
- Diagnose Perplexity native search and tool-argument failure through Lumen; display execution evidence independently of capability support.
- Provide a documented root Compose source-build workflow and smoke command for Afterglow, Lumen, Drover, Waygate and Palimpsest with isolated local databases and safe prerequisites.
- Verify exact model routing and context capacity through that local runtime.
- Replace the simple context tooltip with an accessible composition inspector: included/deferred components, safe source names, token counts and shares, reserves/free capacity, and explicit measurement/provenance limitations.

## Capabilities

### New Capabilities
- Root local extracted-service deployment and integrated smoke checks.
- Owner-scoped context composition inspection using existing context API/events.

### Modified Capabilities
- Chat settings viewport behavior; context disclosure and parsing; native search evidence and failure rendering.

## Impact

Changes span Afterglow frontend/deployment and sibling Lumen context/tool/provider paths. Existing dirty work is preserved. Production credentials and databases must not be modified; Compose uses a distinct project and local databases, and provider proof is bounded and secret-safe. No production deployment, commit or push. Existing persisted context events remain readable. No invented token windows, fake search-success flags or app authentication bypasses.
