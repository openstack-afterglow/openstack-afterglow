## Why

운영1.32.8의 scheduler가 활성화됐지만 기존 VM이 미등록 상태다. 세 API의 실제 설정은 true이고 controller1의 background cycle은 tenant project에 관리자 service credential을 재스코프하려다 Keystone401로 실패한다. Schedule 날짜나 수집 스위치를 다시 쓰는 문제가 아니라 executor 인증 scope와 resource target을 혼동한 경로다.

## What Changes

- 기존 governance가 사용하는 fixed admin-project native executor와 검증된 별도 usage target binding을 background scheduler·managed cleanup에도 재사용한다.
- 일반 exact-project connection의 검증은 유지하고, operator는 원 authenticated admin project/user와 exact bound target을 매번 검증한다. 서버·share의 native 소유권, revision, lease와 무재시도/unknown 경계를 유지한다.
- 임의 tenant role 추가, 인증 우회, 일정 수동 입력·재등록, native IAM/metadata/lifecycle·설정·운영 배포는 하지 않는다.
- 실제 설치 SDK와 loopback Keystone/Nova에서 target password scope401/fixed admin scope 성공을 구분하는 default-factory 회귀를 둔다. 운영은 configured service account의 정상 fixed scope와 해당 VM GET만 읽기 전용 대조한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

기존 usage schedule background enrollment/expiry/managed cleanup의 executor scope가 native admin-project 권한과 별도 target ownership을 일관되게 사용한다. 일정은 계속 Nova metadata가 유일한 정본이다.

## Impact

`services/instance_usage.py`, `instance_usage_scheduler.py`, `instance_usage_cleanup.py`와 관련 회귀·architecture/testing/deployment/changelog. 삭제한 private proof를 import하던 `mail_resource_notifications.py`도 공통 proof 호출로 이관하되 mail의 기존 exact-project 인증 정책은 바꾸지 않는다. API payload·schema·기한 정책·삭제 동의·기존 metadata/revision·운영 키·역할은 변경하지 않는다. Source/local 수용과 운영 릴리스·적용은 별도이며 후자를 자동 수행하지 않는다.
