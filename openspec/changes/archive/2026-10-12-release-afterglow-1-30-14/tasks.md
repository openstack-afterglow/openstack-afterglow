## Implementation Tasks

- [x] 실제 native inventory/controller image·revision·상태와 운영 schema를 읽기 전용으로 수집한다.
- [x] v1.30.13 GPU admission hotfix를 격리 dev에 보존하고 v1.30.14 metadata와 배포 문서를 동기화한다.
- [x] 통합 source gate·실행 smoke·architecture guard를 통과하고 정확한 dev SHA를 정상 push한다.
- [x] 정확한 SHA CI 성공 뒤 immutable v1.30.14 tag를 발행하고 세 version/latest image의 revision·digest·amd64 실행을 확인한다.
- [x] writer census·원래 key/config/plugin/inventory 복구 지점을 보존하고 backup을 실제 격리 DB에 복원하여 SQL084–087 및 old/new writer 호환성을 검증한다.
- [x] 필요한 SQL postcondition만 안전하게 적용하고 canonical Kolla genconfig/pull/prechecks/reconfigure로 Afterglow만 순차 배포한다.
- [x] 세 controller의 실제 version/digest/readiness·공개 auth 경계/UI·unrelated container 보존을 검증한다.
- [x] 배포 receipt·한계를 문서에 기록하고 release change를 archive하여 dev로 push한다.
