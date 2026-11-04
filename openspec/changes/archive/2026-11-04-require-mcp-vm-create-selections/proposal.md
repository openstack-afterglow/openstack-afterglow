## Why
MCP VM creation allowed implicit boot volume sizing and an omitted SSH key, and did not allow selecting security groups. Explicit user-owned access and networking choices are required before creating a VM.

## What Changes
- **BREAKING:** Require explicit SSH key name, boot volume size, flavor, network, image, and one or more security group IDs on MCP VM creation.
- Verify the key belongs to the authenticated user and each security group belongs to the selected project; preserve these choices in preview and the provider request.
- Fail closed before creating resources when selections are missing, inaccessible, invalid, or change before dispatch.

## Capabilities
### New Capabilities
- `mcp-vm-explicit-creation`: Explicit, ownership-verified VM creation selections for consumer MCP.

### Modified Capabilities
- None.

## Impact
MCP VM create schema and consumers, cloud adapter, tests, user and architecture documentation. Existing instances and stored grants are unchanged; rollout is separate.
