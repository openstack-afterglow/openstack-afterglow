## Why

사용자가 승인한 GCP형 구조로 immutable 계정 소속과 리소스 소속을 분리한다. 사용자마다 개인 도메인을 생성하는 현재 경로를 중단하고 모든 신규 human을 `account`, 조직 없는 개인 프로젝트를 공통 `personal`, 조직을 개별 domain으로 구성한다. 조직 참여는 manager 초대 수락 또는 신뢰된 OIDC 자동 가입만 허용한다.

## What Changes

- `account`는 identity-only이며 workspace/Default/IAM tenant가 아니다. `personal`은 프로젝트별 소유권/직접 역할/quota만 사용하고 domain manager/상속 projection/도메인 allocation pool을 사용하지 않는다.
- 모든 human enrollment는 disabled account user와 username+암호학적 난수 개인 프로젝트를 journaled 생성하고 owner/reader·quota readback 후 활성화한다. 이름은 native effect 전에 고정한다.
- 기존 계정은 native ID/home/password/federation/기존 grant·자원을 보존한다. 검증된 최초 human 로그인에서 별도 개인 프로젝트만 준비하며 자동 계정 이동·복제·삭제는 없다. 운영 service/bootstrap identity는 자동 이관하지 않는다.
- 사용자 조직 생성은 공개 계정 가입 정책과 분리된 설정으로 제어하고 생성자를 최초 manager로 만든다. 조직 생성/가입은 기존 canonical Default-manager 권위와 last-manager/owner 경계를 재사용한다.
- 운영자 등록 OIDC 조직은 issuer+stable organization ID에 묶고 명시한 manager subject만 최초 조직을 생성할 수 있다. 공급자 origin·계정 identity·작업 domain은 분리한다. 임의 email/표시 이름으로 조직을 생성하거나 manager를 부여하지 않는다.
- 조직 manager의 직접 사용자 생성/공통 계정 credential 수정과 generic membership/group 우회를 닫는다. 기존 계정 초대는 authenticated one-use acceptance, 신규 계정 초대는 검증된 주소의 account 생성과 명시 조직 admission으로 처리한다.
- 로그인/refresh/workspace selector/API DTO·onboarding/admin/IAM UI와 지원 언어를 전환한다. Native session/JTI/ABA/owner fences와 explicit stable-sub account linking을 유지한다.

## Capabilities

### New Capabilities

- Shared identity-only account domain and isolated per-user primary personal projects.
- Trusted OIDC organization domain provisioning with explicit bootstrap authority and uncertain-effect fencing.

### Modified Capabilities

- Human enrollment, personal quota provisioning, login/default workspace and project creation.
- Organization self-service, member admission, directory visibility and account credential ownership.

## Impact

Backend authority/session/enrollment/provider/project/quota APIs, frontend onboarding/workspace/admin/IAM flows, native metadata and additive SQL migrations are affected. Old writers must be stopped before schema/cutover; unknown/partial native intents are not replayed or silently compensated. Existing schema history and active `secure-global-account-enrollment` live acceptance records remain preserved; this change supersedes its per-user personal-domain source invariant, not its unresolved operational receipts. No commit/push/release/deployment/live schema or identity mutation is authorized by this implementation request. Concurrent header/locale/doc changes remain preserved. Local synthetic provider/native proofs must be reported separately from real external OIDC/SMTP/OpenStack and production qualification.
