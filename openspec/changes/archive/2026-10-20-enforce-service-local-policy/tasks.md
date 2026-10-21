## Implementation Tasks

- [x] OpenStack oslo.policy 기본값·YAML override·scope·표준 생성 도구와 기존 네 서비스 경계를 조사한다.
- [x] Lumen의 native action 인가·capability·설정·운영자 정책 파일 경로를 전환한다.
- [x] Drover의 native action 인가·capability·설정·운영자 정책 파일 및 guest delegation 경로를 전환한다.
- [x] Waygate의 native action 인가·capability·설정·운영자 정책 파일 경로를 전환한다.
- [x] Palimpsest의 native action 인가·capability·설정·운영자 정책 파일 경로를 전환한다.
- [x] Afterglow의 preset service edge 생성·기존 관리 edge 전환·native capability 기반 BFF/UI·설정/배포 소비자를 cut over한다.
- [x] Grade-only/no-service-edge, reader/write deny, cross-service/project/system/key boundary, YAML override/reload, actual API 및 VM user-data 생성 경로를 실행 검증한다.
- [x] 계정/personal/organization 회귀·관련 target·전체 필수 gate를 최종 통합 source에서 실행하고 실제 결과를 기록한다.
- [x] 아키텍처·정책 운영 문서·변경 이력·검증 증거를 갱신하고 완료한 change만 archive한다.

## Verification

- 최종 Afterglow source `2a563789902e6f79d136d063ad971b7dcc8840ede58f7cc268b101b5495262e1`/3393files의 `test:gate` exit0. Native-policy consumer258·auth/access/config target·실제 TLS BFF20checks·compiled 명시적67-edge 전환·108modal 조건과 account 전환 HTTP를 실행했다. Count는 겹칠 수 있으므로 합산하지 않는다.
- Native Lumen focused1036/SQL340/system31/SDK128, Drover full1595/3skip, Waygate full1746/3skip, Palimpsest Hub650/2skip 및 각 actual HTTP·generator·nonroot arm64/amd64 policy 실행 증거를 각 서비스 receipt에 보존했다.
- Lumen full contract의 기존 v2 expired-approval checkpoint1실패와 Drover·Waygate의 관련 없는 기존 lint 실패는 숨기거나 구현을 바꿔 통과시키지 않았다. 자세한 결과·이미지 source 범위·권한/소유권 경계·user-data 측정은 `docs/testing.md`와 `~/.local/share/afterglow-proofs/service-policy-20261020-<service>-019qotth/verification.json`을 따른다.
- 실제 실패 VM payload/Nova 제한·운영 guest custom-policy 배포는 수용하지 않았다. Native 정책 지원→동일 caller allow/deny 수용→명시적 관리자 preset 순서가 운영 전제조건이며 이번 작업은 운영 IAM·배포·publish를 수행하지 않는다.
