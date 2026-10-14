## Implementation Tasks

- [x] 최신 dev에 다섯 저장소의 전체 공개 변경을 누락 없이 통합하고 원본 private/branch/index 및 기존 tag를 보존한다.
- [x] 관측된 storage deletion11개·database PageState type 오류와 통합 중 실제 실패만 최소 수정하고 scope/authorization/fail-closed 계약을 보존한다.
- [x] Exact→related→전체 gate, 실제 runtime smoke·독립 review·architecture freshness 및 patch version/lock/docs를 검증한다.
- [ ] 검증된 전체 source를 dev에 일반 commit/push하고 exact SHA CI/CD를 통과시킨다.
- [ ] CI 통과 SHA에 불변 release tag를 발행하고 선언된 platform image/package 및 latest/stable revision/digest를 검증한다.
- [ ] 운영 baseline/inventory/대상·원래 key·schema/writer/IAM/storage·backup/restore와 recovery point를 확인한다.
- [ ] 필요한 operator package만 정확한 release로 갱신하고 canonical multinode genconfig→pull→prechecks→reconfigure를 수행한다.
- [ ] 모든 대상 서비스 version/digest/readiness·auth와 실제 사용자/Bklit 화면, 비대상 보존을 검증하고 정제된 receipt·docs/archive를 완료한다.
