## Why

사용자가 개인 API 키뿐 아니라 `https://cloud.dmslab.re.kr/mcp/oauth/authorize`에서 로그인·동의를 거치는 실제 MCP OAuth 연결을 요청했다. 기존 운영 authority는 DCR → PKCE S256 authorize → browser consent → authorization-code token exchange → MCP initialize/tools/list 및 refresh rotation까지 실제 pieroot 세션으로 성공했다. 별도 인증 서버나 API 키를 OAuth secret으로 바꾸는 우회는 필요하지 않다. 현재 계정 화면은 개인 키 JSON만 제공하고 OAuth 설정을 설명하지 않으며, pending consent가 프로젝트 선택보다 먼저 반환 목적지로 선택되는 경로를 수정해야 한다.

## What Changes

- 기존 `/mcp/oauth/authorize`, `/token`, `/register`, `/revoke`, discovery와 user/project-bound restricted credential authority를 유지한다.
- 계정의 외부 AI 접근에 Authorization 헤더·개인 키 없이 복사할 수 있는 HTTP OAuth 설정 및 실제 authorize URL을 제공한다. 인증은 클라이언트가 discovery 후 state/resource/redirect/PKCE를 붙여 시작한다.
- `/oauth/mcp/authorize` exact route만 SSR/client public·project-agnostic·shellless로 허용하고 no-store/no-referrer를 보존한다. 미로그인은 기존 로그인으로, 로그인 후 프로젝트가 없으면 프로젝트 선택으로 이동하며 동의 ticket을 유지한다. 프로젝트 확정 이후에만 동의 화면으로 복귀한다.
- refresh 요청에 client_id가 있으면 기존 grant의 보존된 authorization code에서 issuing client를 확인한다. 생략은 허용하되 불일치·빈 값·불명확한 binding은 회전·replay 폐기 전에 거부한다. 단기 code 만료와 ticket cleanup은 장기 refresh binding을 없애지 않는다.
- 공개 MCP 가이드와 네 언어 UI에 OAuth/API 키 선택, 실제 endpoint, scope, refresh·폐기, 클라이언트별 OAuth 예시와 bare authorize URL의 필수 파라미터를 설명한다.
- 실제 운영 OAuth 승인/거절·코드 교환·MCP 읽기·회전·폐기와 개인 키 경계를 확인한다. UI 변경은 격리 빌드 smoke와 불변 patch release를 거친 canonical Kolla로 검증한다.
- 실제 운영 consumer `tools/call`에서 발견한 SDK1.28.1 cold schema-cache refresh의 `None` callback을 처리한다. Public pagination·principal 범위·SDK validation을 유지하고 cold/beyond-page 실제 HTTP 및 cached manage-schema/read-mutation denial을 회귀 검증한다. HTTP200만으로 MCP 읽기를 완료 처리하지 않고 typed 결과와 `isError=false`를 확인한다.

## Capabilities

### New Capabilities

- 계정에서 secret-free OAuth 연결 설정을 복사하고 실제 authorization endpoint를 확인한다.

### Modified Capabilities

- OAuth 로그인 handoff가 프로젝트 선택을 건너뛰지 않고 pending ticket을 보존한다.
- 개인 API 키 방식은 기존 일회성 발급·검증·폐기 계약 그대로 유지한다.

## Impact

Frontend account/consent/login-return helper와 SSR/root layout의 exact OAuth shell 분류, existing OAuth token endpoint/authority의 client binding, MCP transport의 SDK cold schema-cache callback, consumer-visible SQL/UI/SDK regression, localized UI/docs 및 architecture/release 기록에 한정한다. DB schema, delegated roles, service grades, sibling services와 권한 부여 정책은 바꾸지 않는다. 공유 checkout은 보존하고 기존 격리 clone의 dev에서 작업한다. 운영 이미지 획득·설정 생성·배포는 wireguard-dmslab:/etc/kolla의 `kolla-ansible genconfig/pull/prechecks/reconfigure -i /etc/kolla/multinode --tags afterglow`만 사용한다.
