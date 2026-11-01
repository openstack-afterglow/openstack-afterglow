# flavor-automation-policy Specification

## Purpose
Define revisioned administrator approval for exact GPU attachment templates and retained compute-host support, with explicit host retirement through stock Nova APIs and no native source patch.
## Requirements
### Requirement: Explicit host lifecycle
Afterglow MUST retain each verified host's supported inventory across disconnect, disabled/down state and native directory absence until an administrator explicitly marks that exact host removed. Discovery MUST NOT reactivate removed hosts. Explicit retirement MUST disable a still-present native compute service with standard Nova API and verify the result; it MUST NOT delete VMs, hosts or flavors.

#### Scenario: Disconnected or disappeared host
- **WHEN** a previously observed host is down or missing from later Nova/Placement discovery
- **THEN** its saved supported CPU/RAM/GPU inventory MUST remain included and the UI MUST distinguish unavailable observation from administrator removal

#### Scenario: Explicit removal survives rediscovery
- **WHEN** an administrator marks a host removed and it later reappears
- **THEN** its inventory MUST remain excluded until another explicit administrator action

### Requirement: Administrator-approved GPU profiles
Only enabled administrator-saved GPU automation profiles MUST authorize automatic GPU flavor generation. Each profile MUST define a unique stable name, exact per-GPU physical resource requirements and extra specs. Every primary GPU and physical companion MUST be represented by an exact native PCI attachment alias; Placement-only quantities MUST NOT imply attachment. Builtin catalogs, observed devices and inferred names MUST NOT approve profiles. Identical companion aliases MAY recur across profiles only with the same resource mapping.

#### Scenario: Unknown newly connected GPU
- **WHEN** Placement reports a GPU resource with no approved profile
- **THEN** no managed flavor for that GPU MUST be created or published

#### Scenario: Exact variant naming and scaling
- **WHEN** separate 3060, 3060lhr and 4090 profiles are approved
- **THEN** generated names MUST preserve those exact slugs and GPU/companion request counts MUST scale while unrelated approved specs remain unchanged

#### Scenario: Placement-only physical device request
- **WHEN** a profile reserves a physical GPU or companion in Placement without its native attachment alias
- **THEN** approval MUST be rejected rather than generating a flavor that can boot without the device

### Requirement: Revisioned administrator policy
Policy mutations MUST require fresh system-admin authorization, bounded strict input, shared graph fencing and expected revision. Reads MUST be side-effect-free and late browser responses MUST NOT cross authority/scope generations.

#### Scenario: Stale editor
- **WHEN** another administrator updates policy before save
- **THEN** stale mutation MUST return conflict without overwriting the newer profile or host state

