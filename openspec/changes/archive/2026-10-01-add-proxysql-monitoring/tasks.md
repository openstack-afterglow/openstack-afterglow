## Implementation Tasks

- [x] 기존 모니터링·배포 설정 계약과 운영 Grafana ProxySQL 대시보드 UID를 확인한다.
- [x] MySQL을 유지하고 ProxySQL 메뉴·페이지·Grafana 키·API 응답·설정을 추가한다.
- [x] 예시 및 Kubernetes/Helm 설정 렌더링을 동기화하고 기존 API/config 계약 검증을 갱신한다.
- [x] 최신 소스의 실제 Chromium에서 ProxySQL 메뉴 진입·대시보드 임베드·명령 팔레트·반응형 화면과 MySQL 보존을 확인한다.
- [x] 검증 증거에 맞춰 API/설정 문서·아키텍처·변경 이력을 갱신하고 change를 archive한다.

## Verification Evidence

- 기존 Grafana 검색 API의 UID `afterglow-proxysql`을 확인하고 격리 canonical Compose frontend의 실제 Chromium iframe에서 실제 대시보드 패널·그래프와 수집 대상 3개·최소 online writer 1개·백엔드 연결 오류 0을 확인했다. Afterglow 인증 identity만 합성이며 Grafana/Prometheus 응답은 합성하지 않았다.
- MySQL UID 보존, 공유 sidebar/mobile drawer/명령 팔레트 진입과 drawer 닫힘을 확인했다. 390·767·768·1023·1024·1440px에서 문서 가로 overflow 0과 충분한 iframe 크기를 확인했으며 앱 light/dark 화면을 검증했다.
- 관련 Grafana API/settings 7 tests, config target backend 145/frontend 10 tests, design target 110 tests와 frontend check 당시 0 errors/0 warnings를 확인했다. UID default/TOML/environment 우선순위 및 실제 Kubernetes/Helm 렌더링 override를 확인했다.
- arm64/amd64 frontend/backend 이미지 빌드·실행, 격리 frontend health/API router 응답, backend source SHA 일치를 확인했다. 공유 서비스를 재생성하지 않았고 실제 Keystone 인증·OpenStack 변경·운영 배포는 하지 않았다.
- 초기 `npm run test:all`은 unit 단계에서 frontend 5개 suite의 `securityGroupUnion`/`SecurityGroupUnion.svelte` import 오류로 중단되어 contract·functional 단계가 실행되지 않았다. 현재 소스에서 해당 5개 suite를 재검증해 13 tests가 통과했다.
- 후속 `npm run test:gate`의 검증 snapshot은 `1fb7b86073787c20958678bfaa5e01057623d009f8af779990b3a9d0719fea65`다. docs freshness와 unit(backend 3393·frontend 1813 tests), contract 136 tests, 격리 MariaDB/PostgreSQL/Redis functional 28 tests가 통과했다(functional 9 deselected). Functional 전용 서비스는 실행기가 종료·삭제했다.
- Backend `ruff check`는 통과했으나 `ruff format --check`가 `backend/app/main.py`, `backend/app/services/layer_build.py`, `backend/tests/test_logging_contract.py`를 지적해 최종 gate는 실패했다. ProxySQL 변경 범위 밖의 해당 파일을 재포맷하지 않았으며 전체 gate 통과로 보고하지 않는다.
