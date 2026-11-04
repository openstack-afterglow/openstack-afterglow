## Context
운영은 Lumen0.6.12, Drover0.4.15, Waygate0.3.5 및 Palimpsest57ab180 API/worker를 세 controller에서 실행한다. 공유 source checkout에는 미발행 기능이 섞여 있다. 운영 operator package는 Lumen0.6.12/Drover0.4.15/Waygate0.3.5/Palimpsest-client0.3.10이며 root role link와 이미지 revision은 별도로 검증해야 한다.

## Goals / Non-Goals
**Goals:** manager/member 관리, reader 비밀 없는 조회, native 역할/target/credential 경계, 정식 이미지·Kolla 배포와 운영 검증.
**Non-Goals:** Pi/chat/durable engine 전환, 기존 role ID/할당 삭제, read grant 승격, main merge, 데이터/키 교체.

## Decisions
- 공유 dirty checkout을 배포하지 않는다. 최신 native dev와 실제 운영 revision을 비교하고 필요한 권한 변경을 격리 후보에 적용한다. 이미 dev에 합쳐진 무관한 schema cutover는 배포 호환성 문제로 명시적으로 해결한다.
- 사용자 선택: Palimpsest는 운영 기준 별도 release branch 예외 대신 **최신 dev 전체 전환**을 명시 승인했다. 이미 병합된 SDK/publication schema·DB/CAS 변경을 포함하고 복원·호환성 검증과 writer 정지 전환을 추가한다. 다른 세 서비스의 무관한 미발행 기능은 여전히 제외한다.
- native 정책이 최종 권위를 소유한다. Afterglow UI/BFF에서403을 숨기거나 관리자 token을 대체하지 않는다. MCP restricted credential의 실제 native policy endpoint도 검증한다.
- 기존 explicit override는 자동 삭제하지 않는다. 새 등록 기본값과 비교하고 변경이 필요한 정확한 rule만 기록한다.
- 원 DB/Redis/key/mount/port, schema ledger, image rollback identity와 모든 container baseline을 보존한다. 비밀 값 대신 equality/digest를 기록한다.
- 실제 배포는 현재 repository guide의 compute 전체 reconfigure 후 control 전체 tagged reconfigure다. 장기 실행은 durable log/exit/recap을 보존하며 SSH 종료를 배포 성공으로 보지 않는다.

## Risks / Trade-offs
- 오래된 published tag만 기준으로 삼으면 운영 hotfix를 되돌릴 수 있다. 실제 image revision의 ancestry/delta를 먼저 확인한다.
- 최신 dev 전체를 발행하면 무관한 migration을 도입할 수 있다. 버전만 올린 후보와 incomplete policy port를 모두 금지한다.
- manager의 provider 실행은 native role implication/Trust attenuation과 별개다. 실제 허용 role을 임의 발급하지 않고 단독 manager 시나리오를 검증한다.
- 정식 이미지 발행과 운영 수용은 별도 증거다. release 본문은 한영 버전·날짜/시간대·변경·중단/삭제(없음/None 포함)를 명시한다.
