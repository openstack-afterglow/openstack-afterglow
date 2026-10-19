## ADDED Requirements

### Requirement: Omitted restrictions expose all enabled providers

The system SHALL offer all enabled configured file-registry providers and existing enabled configured SQL providers owned by the selected domain when neither the exact domain nor the default specifies `allow_providers`. Provider instances SHALL remain distinct regardless of shared kind.

#### Scenario: Official and self-managed GitLab share a kind
- **WHEN** `gitlab_com` and `dmslab_gitlab` are enabled OIDC registrations and no effective allowlist is configured
- **THEN** both independent provider IDs and names are returned for the domain without an IdP discovery request

### Requirement: Domain allowlists replace inherited restrictions

A non-null `auth.domain.<canonical-ID>.allow_providers` SHALL replace `auth.default.allow_providers`. An omitted domain list SHALL inherit the default list, or unrestricted behavior if the default is also omitted. Explicit empty lists SHALL offer no external provider. The effective list SHALL preserve first-occurrence order and SHALL NOT implicitly append common or SQL providers.

#### Scenario: A domain restricts a globally available registration
- **WHEN** the default permits both GitLab instances and the exact domain permits only `dmslab_gitlab`
- **THEN** only the self-managed instance is offered for that domain

#### Scenario: Explicit empty is different from omission
- **WHEN** one domain has `allow_providers = []` and another has an empty domain table with no default restriction
- **THEN** the first offers no external provider and the second offers all enabled registrations

### Requirement: Allowlist enforcement applies at every provider boundary

The effective allowlist SHALL apply to both file registry keys and canonical SQL IAM provider UUIDs on public listing, authorization, callback, refresh and verification. SQL UUIDs SHALL resolve only within the selected domain. A denied SQL provider SHALL NOT count as a usable replacement when disabling password login.

#### Scenario: A pending login loses allowance
- **WHEN** a provider is removed from an effective allowlist after authorization starts
- **THEN** its callback and provider-bound refresh are rejected and it is not marked verified

#### Scenario: A domain-local SQL provider is not an implicit exception
- **WHEN** an explicit allowlist omits an otherwise enabled and verified SQL provider
- **THEN** its button and direct authorization are denied and it cannot justify disabling password login

### Requirement: Configuration cutover and projection preserve semantics

Settings and generators SHALL reject retired `providers` selector fields, unknown registry references and malformed allowlist values. Generated K8s/Helm runtime configuration SHALL preserve omitted versus explicit empty allowlists and retain secret separation.

#### Scenario: Omission survives deployment generation
- **WHEN** configuration with multiple registrations and no default restriction is rendered for K8s or Helm
- **THEN** reloaded runtime settings remain unrestricted rather than receiving an empty allowlist

#### Scenario: Old additive selector is supplied
- **WHEN** a default or domain contains `providers` instead of `allow_providers`
- **THEN** startup or generation fails rather than silently exposing all registrations

### Requirement: Connections are configured independently of deployment names

The system SHALL select provider instances, issuer/client credentials and native federation IdP/protocol from configuration rather than known domain names, known domain IDs or a GitLab host. Adding an instance of a supported OIDC/GitHub kind SHALL NOT require a source change. Configuration changes SHALL retain the existing startup/restart, secret separation and native identity validation contracts.

#### Scenario: One issuer serves independent native identity domains
- **WHEN** two registry instances share an issuer/application and exact-domain allowlists select distinct configured native protocols
- **THEN** both complete the generic authorization/callback flow only when the native identity belongs to the selected domain and its federation metadata matches the selected IdP/protocol

#### Scenario: Another supported login option is added
- **WHEN** an operator registers another supported instance and updates a domain allowlist, then restarts consumers with the updated configuration
- **THEN** the same generic public/login consumers offer and authorize the new option without a domain-specific or provider-name-specific source branch

