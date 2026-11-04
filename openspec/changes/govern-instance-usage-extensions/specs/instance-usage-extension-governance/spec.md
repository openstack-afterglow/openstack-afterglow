## ADDED Requirements

### Requirement: Domain governed extension decisions
The system SHALL default to automatic extension decisions and allow a verified domain manager to configure manual review for that exact domain. Policy storage errors SHALL fail closed.

#### Scenario: Manual review required
- **WHEN** a project writer requests an eligible extension under manual policy
- **THEN** the system records a pending request without modifying the effective expiry and presents the request for review.

#### Scenario: Authorized reviewer
- **WHEN** a current manager of the owning domain or current administrator of the owning project approves a current request
- **THEN** the system revalidates policy, authority and native schedule revision and applies the extension once with verified readback.

#### Scenario: Ambiguous native outcome
- **WHEN** the native mutation outcome is uncertain
- **THEN** the request remains explicitly unresolved and is not blindly replayed or presented as approved.

### Requirement: Bounded schedule changes
The system SHALL permit a future expiry earlier than the current expiry and SHALL limit each extension to one UTC calendar month from the current expiry with a nonempty reason. The interface SHALL explain that administrators may follow up on an unsuitable reason and that a pending request does not extend service.

#### Scenario: Earlier expiry
- **WHEN** an authorized writer chooses a valid future expiry earlier than the current expiry and no native operation is in flight
- **THEN** the new date is applied with the existing revision and lifecycle fences.

#### Scenario: Extension exceeds limit
- **WHEN** a proposed expiry exceeds one calendar month after the current expiry
- **THEN** the change is rejected regardless of route or approval mode.
