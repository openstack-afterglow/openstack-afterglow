## Why

The light-theme new-chat project footer blends into the canvas. MCP connectivity also needs end-to-end production evidence: registration/discovery alone cannot prove that a Lumen chat dispatches Playwright and Afterglow tools.

## What Changes

- Strengthen only the light-theme project footer's neutral gray fill using existing semantic colors; preserve dark appearance, geometry and project-selection behavior.
- Inspect actual MCP configuration, owner selection, lazy discovery, tool execution and failures. Correct only defects supported by runtime evidence; retain authorization and approval boundaries.
- Repair the observed external OAuth consent500 using verified current-role metadata without dropping still-valid token authority or bypassing caller-only credential issuance.
- Deploy the explicitly requested Playwright service through Zun containers, not a separate VM. Add a named, restricted runtime on one approved compute because Zun1.40 does not expose the required per-container security controls; preserve the default runtime and existing services.
- Qualify an isolated latest-dev patch release, publish immutable artifacts, deploy through the existing Kolla inventory, and monitor real chats and logs.

## Capabilities

### New Capabilities

- Authenticated, run-isolated Playwright MCP service with public-only broker egress, existing Lumen v2 approvals and committed-terminal cleanup. This is operator-owned infrastructure, not a new user authority or automatic delegation.

### Modified Capabilities

- Light-theme new-chat project context separation.
- Existing Lumen MCP connectivity and observed operational acceptance, if a repair is necessary.

## Impact

The footer change is presentation-only. The OAuth repair changes role-metadata verification and safe rejection/cleanup, not schema or caller credential ownership. Lumen's service and Zun runtime/deployment work is tracked in its own repository and must qualify actual browser, network, approval/resume and cleanup behavior before activation. Shared working-tree changes remain untouched. Production rollout must preserve existing data, keys, inventory, unrelated services and recovery references; source, synthetic, Linux-container and production proofs remain distinct. A Docker restart or wider host disruption is not approved by the named-runtime decision.
