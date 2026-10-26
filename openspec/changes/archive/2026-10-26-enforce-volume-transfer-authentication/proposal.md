## Why

운영 v1.30.26 관리자 이전은 configured service-project token으로 생성과 수락을 모두 요청하고 target UUID를 X-Project-Id에만 넣는다. Cinder는 token project에 소유권을 부여하므로 선택한 다른 도메인의 프로젝트가 아닌 서비스 프로젝트로 이동해도 성공으로 표시한다. 사용자 보고의 실제 볼륨은 재현을 위해 변경하지 않는다.

현재 local dev에는 native create와 accept를 분리하고 fresh human의 unscoped session_token에서 목적지 project credential을 자동 취득하여 exact user/home/project/domain 및 owner/status/attachments를 확인하는 미배포 수정이 이미 있다. 이 수정을 보존하고 실제 SDK/HTTP 경계로 보강·검증한다. Keystoneauth1 Session의 기본 allow_reauth=True는 연결/status retry=0과 별개로 HTTP401 뒤 token을 다시 교환하고 POST를 재전송할 수 있다. 이 경로는 검증한 credential과 단일 native submission 계약을 지켜야 한다.

## What Changes

- 기존 목적지 인증 자동 발급과 exact native readback을 유지한다. 이름이 같은 프로젝트도 UUID/domain으로 구분한다.
- Cinder transfer create/accept에서 암묵적인 HTTP401 재인증·POST 재전송을 금지한다. 최초 인증은 정상 수행하고 native 거부를 보존한다.
- 실제 installed SDK와 loopback Keystone/Cinder를 쓰는 endpoint 회귀로 cross-domain target 인증, scoped-root 혼동 방지, 잘못 발급된 scope·native denial, 다른 owner로 완료된 가짜 성공 및401 replay를 검증한다.
- API/architecture/changelog와 검증 증거를 갱신하고 change를 archive한다.

## Capabilities

### New Capabilities

없음. 기존 관리자 이전 기능의 안전한 인증 계약을 완성한다.

### Modified Capabilities

관리자 목적지 인증 및 native transfer의 단일 submission·성공 판정.

## Impact

기존 backend transfer core/wrappers와 해당 pytest, storage target 등록 및 문서만 변경한다. Frontend의 기존 selected domain/project picker·once-only key·uncertain outcome fence는 유지한다. 새 dependency/config/schema/credential store나 임시·영구 role grant, service-account impersonation, native policy 우회는 없다. Source 반영·로컬 synthetic proof와 운영 release/rollout은 별개다. 운영 코드·설정·IAM·보고된 실제 볼륨은 수정하지 않는다. 공유 checkout/index와 다른 세션 변경은 보존한다.
