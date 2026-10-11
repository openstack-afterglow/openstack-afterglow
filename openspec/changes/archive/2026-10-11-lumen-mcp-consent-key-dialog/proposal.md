## Why

Lumen 설정에서 Afterglow MCP의 존재와 위임 범위를 확인·승인할 수 없고, 첫 native 채팅이 읽기 위임을 암묵적으로 생성한다. 관리자 승인 remote MCP는 사용자별 활성화 상태가 없으며 기존 API 키 화면은 발급 폼과 폐기된 목록을 항상 표시한다.

## What Changes

- 기본 Afterglow MCP를 승인된 서버 영역에 항상 표시한다. 기본 비활성, 현재 프로젝트와 읽기/관리 권한을 명시 승인한 뒤에만 서버-held 위임을 생성한다. 기존 개인 키의 명시 선택은 유지하되 암묵적 Lumen grant는 새 승인 없이 실행하지 않는다. 비활성화·만료·권한 철회는 기존 execution fence를 따른다.
- 관리자 승인 global remote MCP를 사용자·프로젝트별 opt-in 연결로 제공한다. 활성화 버튼에서 대상 URL·요청 OAuth scopes를 검토하고 필요하면 기존 OAuth 승인으로 연결한다. 관리자 설정 변경은 이전 승인 효력을 없애고 직접 사용자 MCP 추가는 유지한다.
- 폐기된 Lumen API 키를 기본 숨기고 전체 보기/활성만 보기 버튼으로 전환한다.
- 새 API 키 발급 버튼은 FormModal을 연다. 이름, 프로젝트, 만료, 전체/제한/읽기 권한, 월 크레딧 한도를 한 번에 선택한다. 실제 native Lumen 저장·인증에서 만료를 강제한다. 기존 키는 무만료 상태를 유지한다.

## Capabilities

### New Capabilities

- Explicit project-bound built-in cloud MCP approval.
- Owner-bound activation for administrator-approved remote MCP sources.
- Expiring ordinary Lumen API keys with atomic issuance limits.

### Modified Capabilities

- Lumen chat settings MCP catalogue and API key issuance/list visibility.

## Impact

Afterglow owns browser consent, authenticated BFF and Keystone delegated credentials. Lumen owns remote MCP activation, ordinary key persistence, expiry and execution gates. Afterglow migration086 adds nullable consented_at without legacy approval backfill; Lumen migration026 adds owner/project activation without backfill. Ordinary key expiry reuses the existing nullable expires_at column from migration013; no duplicate expiry DDL is introduced. Apply schema before coordinated API/worker cutover: old writers cannot enforce new consent/activation/expiry contracts and mixed-version rollout is not qualified. Existing data, secrets, production services and concurrent changes are preserved. Verification uses actual local source runtimes and isolated datastores with synthetic identity/provider boundaries; no paid inference, production IAM mutation or deployment.
