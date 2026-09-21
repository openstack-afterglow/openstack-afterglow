## ADDED Requirements

### Requirement: Discovery describes compatibility and Gateway contracts
Discovery SHALL publish the supported OpenAI Responses, OpenAI Chat Completions, Anthropic Messages, native API, and enabled Gateway endpoints with their authentication mode, required scopes, stream framing, terms version, verification URI, and compatibility limitations. Disabled Gateway endpoints SHALL NOT be advertised as usable.

#### Scenario: Gateway enabled
- **WHEN** discovery is requested from an allowed public host and Gateway is enabled
- **THEN** the response includes device authorization, token, refresh, verification, consent, CLI, and auth-mode metadata without secrets

#### Scenario: Gateway disabled
- **WHEN** Gateway is disabled
- **THEN** discovery omits an enabled Gateway profile and the device endpoints fail closed

### Requirement: Every deployment surface carries the same Gateway configuration
Lumen Compose, Kolla, and Afterglow-managed Kubernetes/local-service manifests SHALL expose equivalent enablement, public verification URI, public client ID, terms version, and device/access/refresh TTL settings. Service startup SHALL validate unsafe or incomplete production combinations.

#### Scenario: Production HTTP verification URI
- **WHEN** Gateway is enabled outside loopback development with an `http://` verification origin
- **THEN** deployment precheck or application configuration rejects startup

#### Scenario: Migration ordering
- **WHEN** an operator enables Gateway or active-path reads
- **THEN** documented deployment order applies Lumen migrations before API/worker start and verifies the new tables/projection before serving traffic

### Requirement: SDK transports preserve opaque pagination values
Both the httpx API-key client and OpenStack SDK proxy SHALL pass `before` and `after` cursors unchanged and expose the new message-page fields without converting them to numeric IDs.

#### Scenario: SDK newer-page request
- **WHEN** a caller passes an opaque `after` cursor through either SDK transport
- **THEN** the request query contains the exact cursor string and the returned page preserves all edge metadata

### Requirement: Operations guidance distinguishes readiness and proof
Documentation SHALL state that process health does not prove migrations, worker readiness, projection integrity, device login, or external provider completion. Verification claims SHALL distinguish synthetic provider/system proof from live provider or deployed OAuth proof.

#### Scenario: Operator rollout checklist
- **WHEN** an operator follows the documented rollout
- **THEN** the checklist includes migration checksum, projection integrity, device login/rotation/revocation, API/worker readiness, and compatibility request verification as separate checks
