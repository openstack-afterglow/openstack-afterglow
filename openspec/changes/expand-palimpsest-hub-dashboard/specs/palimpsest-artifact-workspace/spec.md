## ADDED Requirements

### Requirement: Independent Hub, native package and local-use workspaces
Afterglow SHALL expose independent Hub images/layers, native packages/keys and local-use tabs on `/palimpsest/packages`. Native protected-identity denial SHALL remain local to native content and SHALL NOT grant or block legacy Hub authority. Existing package ownership and one-time-secret lifetimes SHALL remain enforced.

#### Scenario: Native administrative identity is rejected
- **WHEN** native project context returns its protected-identity 403
- **THEN** the native tab explains that policy and does not issue or reveal package credentials
- **AND** Hub reads and local instructions remain independently reachable under their own authority.

#### Scenario: Loaded native search has no match
- **WHEN** a client-side filter matches no loaded package and a next cursor exists
- **THEN** the UI identifies loaded-only search and retains the load-more action.

### Requirement: Truthful bounded Hub observations
Hub reads SHALL use current browser identity, current service authority and verified Hub capabilities. Search SHALL be server-side and bounded, with independent inventory/detail/build/export failure states. Shared/public rows SHALL retain native Hub visibility. Recent jobs and page sizes SHALL NOT be represented as totals or service health.

#### Scenario: Current permission authority is unavailable
- **WHEN** permission loading, directory failure, token rotation or caller/project transition invalidates a snapshot
- **THEN** stale data/actions are masked and late responses cannot republish authority
- **AND** a later verified grant reloads permitted reads without reviving denied state.

#### Scenario: User inspects an orphan artifact
- **WHEN** a visible artifact has an incomplete ancestor chain
- **THEN** full digest, configuration and chain completeness are available
- **AND** the UI offers no VM launch action for that artifact.

#### Scenario: Browser download cannot be verified
- **WHEN** metadata/stream/header size exceeds 64 MiB, byte length or SHA-256 differs, verification support is absent, or authority changes
- **THEN** the file is not saved and no unverified fallback is used.

### Requirement: Separate local client credentials and explicit authority
Local instructions SHALL use the original SDK account with verified HTTPS and exact project checks, never an Afterglow browser JWT or service-identity substitution. Native package setup SHALL distinguish the public key UUID from the private secret and require an explicit same-authority HTTPS API base.

#### Scenario: Legacy CLI default scope differs
- **WHEN** the original SDK project differs from the selected project or native Hub default user/project differs from the SDK access
- **THEN** legacy inventory/pull stops before execution
- **AND** project-scoped local web control is an explicit option in that same SDK subprocess.

#### Scenario: Registry alias already exists
- **WHEN** native profile creation fails
- **THEN** generated shell commands do not proceed to login against the old profile
- **AND** valid bracketed IPv6 authorities remain supported without inferring an API path.

#### Scenario: Local foreground web is selected
- **WHEN** the user starts local web from the guide
- **THEN** read-only and explicitly opted-in control modes are distinguished, original token/project are inherited only by the child, and remote Hub observations are not presented as local VM state.
