## Why

관리자가 새로 만든 서버 온도 / CPU · 메모리 · 전체 센서 Grafana 대시보드를 Afterglow 관리자 페이지에서도 조회해야 한다.

## What Changes

관리자 모니터링의 노드 다음에 서버 온도 목적지 `/admin/monitoring/temperatures`를 추가한다. 기존 GrafanaEmbed fill과 관리자 전용 catalog를 사용한다. Catalog key `node-temperatures`, 기본 UID `kolla-node-temperatures`; 기본 최근 6시간, browser timezone, auto refresh, job/instance/chip/sensor 전체를 사용한다. Datasource는 원 Grafana dashboard의 기본 설정을 사용하여 운영 고유 datasource ID를 앱에 고정하지 않는다.

## Capabilities

### New Capabilities

- 관리자 서버 온도 대시보드 조회.

### Modified Capabilities

- Grafana UID 설정과 Kubernetes/Helm 생성 경로 동기화.

## Impact

기존 관리자 인증, CSP, theme, responsive navigation 재사용. 신규 exporter, 수집 query, DB/schema, cloud write, 운영 배포 없음. 한국어 및 등록 언어 label을 추가하고 API 설정 우선순위와 실제 화면을 검증한다.
