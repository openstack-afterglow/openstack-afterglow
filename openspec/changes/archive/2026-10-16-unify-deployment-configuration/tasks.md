## Implementation Tasks

- [x] Cloud Shell defaults와 Kolla 생성 layer·env·runtime 소비자 및 기존 setup/K8s/Helm 경로를 조사한다.
- [x] Cloud Shell의 image/pull policy/registry ID 기본값을 모든 생성·설정 경로에 일치시킨다.
- [x] Kolla globals/passwords 자동 생성과 sparse operator TOML의 최종 우선순위를 runtime/bootstrap/policy/worker/frontend/precheck까지 이행한다.
- [x] K8s의 기본 afterglow.conf 기반 자동 생성 및 기존 local/override 보존을 구현한다.
- [x] Helm의 기본 afterglow.conf 기반 자동 생성 및 K8s와 일관된 설정·비밀 처리를 구현한다.
- [x] 기존 setup TUI의 로컬 설정 편집과 배포 파일 생성을 정본 generator에 통합하고 curl GitHub entrypoint를 제공한다.
- [x] 실제 Ansible·CLI·TUI/PTY·다운로드 경로·secret boundary와 영향받는 image의 지원 architecture 및 안전한 runtime 경로를 검증한다.
- [x] 문서·changelog·architecture와 source/publication/운영 증거 경계를 갱신하고 OpenSpec을 완료 처리한다.
