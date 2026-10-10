## ADDED Requirements

### Requirement: Existing direct system authority is verified accurately

Native service authority SHALL recognize a current direct system:all grant of the unique global admin role through the validated current role-ID graph even when Keystone effective expansion omits system rows. Current enabled user/project checks, action gates, key attenuation and nonverified project/domain admin denial SHALL remain intact.

#### Scenario: Existing direct system administrator
- **WHEN** the current directory contains a direct system:all admin assignment and current identity is enabled
- **THEN** native read and administrator actions recognize that existing system authority without changing role grants

#### Scenario: Project admin is not a system administrator
- **WHEN** only project/domain admin labels exist without verified system authority
- **THEN** native global administrator access remains forbidden

### Requirement: Service denial is not session expiry

The frontend SHALL preserve a valid browser session on downstream Lumen403, explain the service authorization denial on the current surface, and reserve authentication recovery for genuine first-party401. Chat permission loading SHALL finish in success or an explicit error state rather than permanent or repeated loading.

#### Scenario: Administrator service403
- **WHEN** a valid first-party session receives a downstream service403
- **THEN** it is not labeled expired authentication or redirected to overview as an authentication workaround

#### Scenario: Chat permission failure
- **WHEN** project permission loading fails or the project changes during the request
- **THEN** loading settles to the current project's safe error state and stale results do not overwrite a newer project
