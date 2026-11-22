## MODIFIED Requirements

### Requirement: Keystone reachability precheck accepts versioned and discovery endpoints
Before Afterglow reconfiguration, the role SHALL verify that every Afterglow controller can reach the effective Keystone endpoint. HTTP 200 SHALL be accepted only when its JSON document advertises a v3 version. HTTP 300 SHALL be accepted only when its discovery document advertises a v3 version. Other HTTP statuses, malformed or non-Keystone documents, TLS failures, and connection failures SHALL block reconfiguration. The role SHALL work with Kolla's unversioned default `keystone_internal_url`; it SHALL NOT require a `globals.d` override solely to append `/v3`.

#### Scenario: Kolla default endpoint returns version discovery
- **WHEN** the effective URL is an unversioned Keystone root returning HTTP 300 with a v3 version entry
- **THEN** the precheck passes without a `globals.d` override

#### Scenario: Explicit v3 endpoint returns a version document
- **WHEN** the effective URL ends in `/v3` and returns HTTP 200 with a v3 version document
- **THEN** the precheck passes

#### Scenario: A non-Keystone or unavailable endpoint responds
- **WHEN** the endpoint returns a non-v3 300, a 5xx, malformed JSON, or cannot be reached
- **THEN** the precheck fails closed
