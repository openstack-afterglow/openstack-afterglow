## ADDED Requirements

### Requirement: Account credit is distinct from usage
The administrator provider settings page SHALL present an explicit `계정 크레딧` state separately from Lumen-attributed usage and official organization cost reports for every provider with a billing snapshot. The page MUST NOT calculate remaining credit, purchased credit, or account balance from usage totals.

#### Scenario: Provider reports account balance
- **WHEN** a DeepSeek snapshot contains currency-specific total, purchased, and granted balances
- **THEN** the provider card displays those exact values as provider-reported account credit with the returned currency

#### Scenario: Provider reports key limit
- **WHEN** an OpenRouter snapshot contains limit and remaining values
- **THEN** the provider card labels them as the configured API key's spending limit and remaining limit rather than account-wide balance

#### Scenario: Provider reports only organization usage
- **WHEN** an OpenAI or Anthropic snapshot contains official usage or cost data but no official balance data
- **THEN** the provider card displays the usage data and separately states that account balance and purchased credit are not exposed by the official API

### Requirement: Credit support state is truthful
The page SHALL distinguish provider-reported credit, unavailable credit lookup, and unsupported programmatic credit lookup. Missing or unsupported values MUST NOT be displayed as zero.

#### Scenario: Supported lookup fails
- **WHEN** a provider with a documented credit capability returns an unavailable billing snapshot
- **THEN** the account-credit section displays a retryable provider lookup failure and no numeric balance

#### Scenario: Provider has no documented balance endpoint
- **WHEN** a provider snapshot does not expose account credit through its supported API
- **THEN** the account-credit section displays `공식 API 조회 미지원` and explains that the official billing console is authoritative

#### Scenario: Billing snapshot is absent
- **WHEN** no billing snapshot is available for a configured provider
- **THEN** the card keeps provider management available and does not fabricate a credit state

### Requirement: Official credit management remains reachable
The account-credit section SHALL show the provider's billing or credit-management action when the billing snapshot supplies a valid HTTPS URL, using the shared button primitive and an opener-safe new browsing context.

#### Scenario: Trusted billing URL exists
- **WHEN** the billing snapshot contains an HTTPS billing URL
- **THEN** the account-credit section renders a visible action that opens the official provider console in a new browsing context without opener access

#### Scenario: Billing URL is unsafe or absent
- **WHEN** the billing URL is non-HTTPS, invalid, or absent
- **THEN** the page renders no external credit-management action for that provider

### Requirement: Credit state preserves responsive parity
The account-credit state SHALL remain readable and actionable at mobile, tablet, and desktop breakpoints in both themes using existing semantic tokens and primitives.

#### Scenario: Narrow viewport
- **WHEN** the page is viewed below 768 pixels
- **THEN** credit values, explanations, and the billing action stack without horizontal page overflow or loss of information

#### Scenario: Tablet and desktop viewport
- **WHEN** the page is viewed at or above 768 pixels
- **THEN** comparable credit values align in the existing responsive grid while retaining the same labels and actions as mobile
