## Why

VM 생성에서 이미지가 Flavor보다 먼저 선택되어 CPU VM에도 불필요한 GPU 드라이버 이미지가 선택되기 쉽다. 부팅 볼륨의 자동 스냅샷·자동 백업도 생성 시 설정할 수 없다.

## What Changes

- 사용자·관리자 VM wizard를 Flavor → 이미지/기존 볼륨 → 설정 → 검토 순서로 전환한다. 선택/프로젝트 전환/최종 admission 검증과 tutorial 연계를 보존한다.
- Glance의 명시적 GPU 드라이버/vendor metadata를 이미지 목록에 전달하고 Flavor에 맞는 current active image 추천을 표시한다. CPU는 일반 이미지를 우선하고 GPU 드라이버 이미지 사용의 불필요한 오버헤드를 경고한다. 추천은 선택을 강제하거나 자동 교체하지 않는다.
- 새 부팅 볼륨 용량 옆에 독립적인 자동 스냅샷·자동 백업 opt-in을 제공한다. 기존 달력 기반 백업의 예약/보존·분산 실행 안전장치를 재사용해 자동 스냅샷을 구현한다. 기본 예약·보존 값을 명시하고 실행 중 볼륨의 crash-consistency 위험에 대한 명시적 동의를 받는다.
- 서버 생성 성공 전 새 부팅 볼륨에 선택한 정책을 등록하며 관측 가능한 실패 시 요청 소유 정책과 이번 생성 자원을 보상 정리한다. 기존 볼륨은 기존 정책을 변경하지 않는다. Redis ACK 유실과 정리 불가/process crash가 겹친 경우까지 포괄하는 다중 시스템 원자적 복구는 보장하지 않는다.

## Capabilities

### New Capabilities

- 명시적 GPU driver image 추천 및 새 부팅 볼륨 생성 시 자동 스냅샷·백업 opt-in.

### Modified Capabilities

- VM 생성 순서와 스케줄러의 Cinder snapshot 지원. 기존 backup 정책 저장값·API의 기본 동작은 보존한다.

## Impact

Frontend wizard/store/image selector와 네 locale, Glance image projection, instance request/orchestration, Cinder snapshot scheduling 및 관련 계약/문서에 영향이 있다. 새로운 SQL schema/migration·cloud credentials·운영 설정 변경이나 배포는 없다. 동시 작업이 많은 공유 dev checkout과 index를 보존한다. 검증은 국소 contract/관련 target, 실제 local HTTP smoke 및 합성 identity/API의 실제 Chromium responsive UI로 한정하며 live OpenStack acceptance로 보고하지 않는다.
