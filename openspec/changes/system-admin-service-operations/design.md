## Context

Afterglow와 Lumen·Drover·Waygate·Palimpsest의 leaf 인가는 system 관리자 예외를 일부 포함하지만 target membership/rescope 및 Palimpsest의 명시적 admin 금지가 앞에서 막는다. 사용자는 별도 선택에서 요청자의 대상 프로젝트 멤버십도 요구하지 않는 전체 관리 실행을 승인했다.

## Goals / Non-Goals

**Goals:** 기존 역할 경로를 보존하고 현재 system:all admin에게 네 서비스의 프로젝트별 전체 관리 작업을 대상 멤버십 없이 허용한다. Caller와 target·executor를 분리하고 요청·durable 실행 시 현재 권한을 검증한다.

**Non-Goals:** 운영 배포/IAM 변경, service account로 caller 대체, 역할 자동 부여, 위조 header 기반 관리자 판정, API key scope 확대, provider 상태 안전 조건 우회.

## Decisions

- BFF의 네 service namespace 및 현재 프로젝트 권한 조회에서 system 관리자의 no-membership target을 지원한다. Target은 선택 도메인의 enabled 프로젝트여야 한다. 기존 admin route 경계는 보존한다.
- BFF의 관리자 대체 인가는 cache flag만 사용하지 않고 기존 `require_admin`으로 native session·현재 system 권한을 새로 검증한다.
- 네 서비스 모두 `X-Project-Id`는 caller connection project, `X-Target-Project-Id`는 별도 logical target이다. Native는 이를 독립 검증한다. Browser의 system claim/header는 입력 권한이 아니다.
- Drover·Waygate admin provider 실행은 명시적으로 구성된 전용 executor의 실제 target credential을 사용한다. Executor와 requester를 별도 기록하고 전송 직전 requester system 권한, executor enabled·provider-only target roles, exact resource/project와 job claim을 검증한다. 일반 사용자의 caller Trust 경로는 유지한다. Executor identity/credential/target member가 미설정이면 접수 전에 명시적으로 거부한다.
- Runtime IAM 자동 역할 부여·service/default identity fallback·caller impersonation은 없다. Operator는 전용 executor를 필요한 target의 native provider roles에만 사전 등록한다. 요청자는 target member를 가질 필요가 없다.
- Lumen은 기존 configured provider executor와 실제 requester journal·pre-I/O authority 경계를 재사용한다. Palimpsest는 human system admin용 명시 context를 사용하고 scoped package keys/machine principals의 ceiling은 확대하지 않는다.

## Risks / Trade-offs

- Keystone Trust는 caller가 대상 프로젝트에서 가진 역할만 위임한다. 새 admin 실행은 requester의 불가능한 Trust를 위조하지 않으며, executor 실제 자격과 requester 감사·회수 경계를 함께 검증한다.
- 네 서비스와 BFF가 동일 header 계약을 지원해야 한다. Drover·Waygate의 additive executor schema/config와 기존 queued caller 경로의 호환성 및 drain-before-upgrade를 검증·문서화한다. Mixed-version은 qualified 전까지 허용하지 않는다.
- UI의 서버 기반 permission 상태·loading/error fence는 유지한다. Client flag만으로 버튼을 활성화하는 우회는 만들지 않는다.
