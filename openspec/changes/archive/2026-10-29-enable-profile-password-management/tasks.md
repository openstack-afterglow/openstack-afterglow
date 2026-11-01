## Implementation

- [x] 기존 비밀번호 변경의 native 권한 경로를 분석하고 본인 변경 경로를 수정한다.
- [x] 외부 계정 최초 비밀번호 생성의 기존 credential 보호와 본인 증명을 구현한다.
- [x] Keystone28.1 SQL guard·모든 password writer의 Galera 인증 충돌 및 권한 경계를 구현한다. (실제 Keystone/Galera 2노드, arm64·amd64 각각 63 passed. 생성자 선행 경합의 errno 1213은 확장의 `unavailable()`이 삼킨 예외 chain에서만 관측됐고 creator/peer engine hook에서는 관측되지 않았다.)
- [x] 메일 전달·발급 후 새 federated session·15분 proof와 자동 재전송 불가 journal을 구현한다.
- [x] 결과 불명의 관리자 전용 명시 settlement와 감사 기록을 구현한다.
- [x] 프로필 화면에 실제 서버 상태에 맞는 생성·변경 및 오류 안내를 제공한다.
- [x] 영향받는 API·아키텍처·사용자 문서와 변경 이력을 갱신한다.

## Verification

- [x] 관련 backend 인증·권한 회귀와 native transport smoke를 검증한다.
- [x] 실제 브라우저에서 생성·변경 및 권한·실패 상태를 검증한다. (합성 API·OIDC callback)
- [x] 관련 테스트와 사용 가능한 프로젝트 검증을 수행하고 제한을 기록한다. 이전 snapshot의 backend213/auth1165·frontend668/fullbackend10525·95skip/frontend5583/contracts183/functional167 등의 과거 receipt는 보존한다. 당시 stale architecture·ignored-config DNS teardown6errors·full test:gate 미실행은 해소된 것으로 소급하지 않는다. 2026-10-30 후속의 정본은 affected auth39modules1333passed, actual HTTP/TLS/native/Galera·compiled browser와 dual-arch password snapshot이며 docs/testing과 외부 proof에 경계를 기록했다. 전체 test:gate/운영 수용은 실행·승인 범위가 아니다.

사용자가 Keystone 원자적 최초 생성 보장을 선택했다. 생성은 소스 구현이며 실제 IdP·메일함·운영 Keystone/Galera 토폴로지와 배포 수용은 별도다.

## 2026-10-30 사용자 요구 후속

- [x] Password 로그인 로컬 사용자의 변경 기능을 관리자 directory·SMTP·최초 생성 extension 장애에서 분리한다.
- [x] 외부·매핑 계정은 실제 native credential history로 생성/변경을 분기하고 조건부 native reset으로 기존-password 메일 복구의 최초 생성 우회를 차단한다.
- [x] 본인 프로필에서 등록 메일의 일회용 변경 폼 링크 요청과 관리자 문의를 제공한다.
- [x] 관리자 exact-user 난수 비밀번호 재설정·등록 메일 자동 전송과 전달/회수/불명확 결과 구분·비밀 미기록을 구현한다.
- [x] 관련 API/security 회귀·실제 native/HTTP·compiled browser 경로를 격리 검증하고 문서·architecture·source compatibility를 기록한 뒤 archive한다.

## 최종 수용 경계 (2026-10-30)

- Current affected auth39modules1336passed, 최신 mapped-state21case와 actual Uvicorn TCP까지 통과했다. API/TLS/native HTTP·Redis smoke, pinned Keystone/Galera128passed per arm64/amd64와 양쪽 actual TCP credential transitions를 검증했다. 범위 중복은 합산하지 않는다.
- Compiled profile/admin/recovery와9locale·responsive/light-dark, Linux sandbox112UI regression,4GiB Linux typecheck0errors/16warnings와 bounded canonical frontend dual-arch profile을 검증했다.2GiB build/typecheck 실패 receipt를 보존하며 full gate/운영 readiness로 확대하지 않는다.
- Canonical backend/worker/frontend의 fresh dual-architecture app stage와 exact password source equality를 기록한다. Matching dependency-only cache 재사용이며 cold acquisition·무관한 동시 source 전체의 release qualification은 아니다.
- 새 schema/migration/config/dependency·운영/공유 native password·메일함·IAM·서비스 교체·commit/push·index 변경은 없다. 기존103/native v1 guard 선행·APIv2 cohort/drain과 실제 operator qualification이 필요하다. 관리자 credential 메일의 mailbox보관 위험과 native expiry 정책을 숨기지 않는다.
