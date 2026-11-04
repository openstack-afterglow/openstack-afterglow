# mcp-vm-explicit-creation Specification

## Purpose
TBD - created by archiving change require-mcp-vm-create-selections. Update Purpose after archive.
## Requirements
### Requirement: Explicit VM creation selections
MCP VM creation MUST require an image, flavor, network, boot volume size, a user SSH key name, and at least one security group ID; omitted, null, invalid, empty, or duplicate selections MUST be rejected before resource creation.

#### Scenario: Missing access or configuration
- **WHEN** a VM creation request omits the key, boot volume size, or security groups
- **THEN** it is rejected without creating provider resources

### Requirement: Exact ownership and safe provider request
The selected key MUST be proven by unseeded provider evidence to belong to the authenticated user, and each selected security group MUST be proven to belong to the selected project. Preview and final dispatch MUST validate the selections, and the approved fingerprint and native VM request MUST include them.

#### Scenario: Unauthorized or changed selection
- **WHEN** a selected key or group is foreign, absent, or cannot be proven at preflight or dispatch
- **THEN** the server does not send a Nova create request

#### Scenario: Valid selection
- **WHEN** all selections are authorized and creation is approved
- **THEN** the single provider request contains the selected key and exact security groups, image-backed volume size, flavor and network
