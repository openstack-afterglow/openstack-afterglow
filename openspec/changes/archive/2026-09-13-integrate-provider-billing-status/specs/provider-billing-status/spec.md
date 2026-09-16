## ADDED Requirements

### Requirement: Unified provider billing load
The administrator provider settings page SHALL request `GET /api/v1/chat/admin/providers/billing` once and map the returned snapshots to configured providers by stable numeric ID.

#### Scenario: Provider and billing loads succeed
- **WHEN** the settings page loads configured providers
- **THEN** each provider row displays the matching billing snapshot without issuing per-provider billing requests

#### Scenario: Billing load fails
- **WHEN** the billing endpoint is unavailable
- **THEN** provider CRUD remains usable and the page shows a retryable billing-status message without treating the provider list as failed

### Requirement: Truthful provider financial status
Every configured provider row SHALL show Lumen-attributed monthly usage, request count, and token count. It SHALL show live provider quota/balance only when returned by Lumen and SHALL explicitly state when automatic balance lookup is unsupported or unavailable.

#### Scenario: Provider supports live balance
- **WHEN** a snapshot has available OpenRouter or DeepSeek balance data
- **THEN** the row displays provider-reported remaining credit/quota alongside separately labeled Lumen usage

#### Scenario: Provider is portal-only
- **WHEN** a snapshot reports unsupported live balance lookup
- **THEN** the row displays local usage and explains that remaining credit must be checked in the official provider console

### Requirement: Safe payment and usage actions
The page SHALL render external billing and usage actions only for HTTPS URLs returned by Lumen, using shared Button primitives and a new browsing context without opener access.

#### Scenario: Official billing URL is available
- **WHEN** a snapshot contains a trusted HTTPS billing URL
- **THEN** a visible `크레딧 충전·결제` action opens it with `target="_blank"` and `rel="noreferrer"`

#### Scenario: No billing URL is available
- **WHEN** a local or unknown provider has no billing URL
- **THEN** no payment action is rendered

### Requirement: Responsive and themed status composition
Billing status SHALL preserve information and action parity on mobile, tablet, and desktop in both light and dark themes using existing semantic tokens and primitives.

#### Scenario: Narrow viewport
- **WHEN** the provider page is viewed below 768px
- **THEN** usage metrics and actions stack without clipping, horizontal page overflow, or hover-only information
