## Why

운영 Grafana에 이미 구성된 `ProxySQL — MariaDB 접속 경로` 대시보드를 Afterglow 관리자 모니터링에서도 확인해야 한다. Grafana 검색 API에서 UID `afterglow-proxysql`과 `afterglow` 폴더를 확인했다.

## What Changes

- 관리자 모니터링의 MySQL 다음에 ProxySQL 항목과 `/admin/monitoring/proxysql` 페이지를 추가한다. 공유 탐색 설정을 사용하여 사이드바와 명령 팔레트에 함께 노출한다.
- 기존 `GrafanaEmbed`와 인증된 `/api/v1/grafana/dashboards` 응답에 `proxysql`을 연결한다.
- `[monitoring.dashboards].proxysql_uid`와 `GRAFANA_DASHBOARD_PROXYSQL_UID`를 지원하고 기본 UID는 기존 운영 대시보드의 `afterglow-proxysql`로 둔다. 예시와 Kubernetes/Helm 렌더링을 동기화한다.
- 현재 MySQL 및 다른 대시보드와 기존 인증·CSP·Grafana 임베드 방식을 유지한다.

## Capabilities

### New Capabilities

- 관리자 콘솔의 ProxySQL 모니터링에서 기존 MariaDB 접속 경로 대시보드를 확인한다.

### Modified Capabilities

- Grafana 컨텍스트의 대시보드 UID 목록에 ProxySQL 설정을 추가한다.

## Impact

- 프론트엔드 모니터링 경로·공유 메뉴·Grafana 키 타입, 백엔드 설정·기존 API 응답, 배포 설정 렌더러가 변경된다.
- 새로운 exporter, Prometheus 쿼리, 대시보드 JSON 복제, DB schema, 인증 권한 변경은 없다.
- 운영 배포·commit·push는 범위 밖이다. 실제 Grafana는 읽기 전용으로 확인하고 로컬 최신 소스에서 메뉴·임베드·반응형 동선을 검증한다.
