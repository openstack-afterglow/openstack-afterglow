## Why

Administrator randomized reset can now create an SSO user's first local password, but its confirmation still assumes an existing password and omits the IdP MFA/deactivation bypass warning. Receipt verification was exercised over real TLS with an explicitly synthetic protocol fixture; independent server interoperability adds evidence without using a real mailbox.

## What Changes

- Correct administrator password confirmation in all nine locales: initialize when absent, otherwise replace, warn about local-password bypass of IdP MFA/deactivation and mailbox exposure.
- Keep provider error mapping coverage behavioral/actual-rendered rather than reintroducing obsolete literal-wording tests.
- Qualify saved-settings connection checks, test-send and exact read-only receipt checks against a throwaway GreenMail standalone server with verified TLS, including substring-search collision and missing-message cases.
- No runtime authority/schema/API change, production mail or service deployment.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `sso-password-recovery`: Administrator confirmation accurately explains both initial creation and existing reset and warns of the SSO security tradeoff.

## Impact

Localized administrator warning and existing security/design/testing/changelog documentation; independent local test evidence. Preserve all current concurrent source and index. Existing full gate, canonical-image and synthetic fault-injection evidence remain correctly scoped and are not rerun as production acceptance.
