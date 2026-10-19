## Why

기존 시스템·리소스 모니터링은 Nova inventory/할당량, Prometheus/libvirt/node exporter를 사용한다. Ceilometer가 Gnocchi에 수집한 실제 OpenStack 지표가 있어도 읽지 않아 상세 시계열을 활용하지 못한다. Native telemetry가 없는 환경의 기존 관측은 계속 유지해야 한다.

## What Changes

- 현재 caller의 Keystone catalog `metric` endpoint와 인증 session으로 Gnocchi를 자동 발견한다. 현대 Ceilometer는 수집기이며 제거된 Ceilometer REST API를 가정하지 않는다.
- Instance 시계열·summary/list badges, project dashboard 추세·resource usage, system monitoring의 실제 native measurements를 통합한다. Gnocchi를 우선하고 기존 Prometheus/node/libvirt/DCGM 데이터를 지표별 대체 수집원으로 유지한다.
- Ceilometer의 instance/instance_disk/instance_network_interface 및 배포에 존재하는 호스트·스토리지 resource/metric을 읽는다. CPU ns counter는 유효한 인접 표본과 vCPU 분모로 정규화하며 byte/request/packet counter도 reset·gap을 구분하여 rate로 변환한다. 메모리 할당과 실사용, 게스트 filesystem과 host disk allocation은 혼동하지 않는다.
- API와 화면에 지표별 source/unit/availability를 표시한다. Native 서비스 없음, 금지, 미수집, 부분 응답, 실패와 실측 0을 구분한다. Native 원본 metadata·토큰·내부 exception body는 공개하지 않는다.
- Native 지표를 포함하는 응답은 caller/project 경계에서만 공유하며 기존 전역 inventory 캐시로 native policy를 우회하지 않는다. 시스템 지표는 기존 시스템 관리자 경계를 유지한다.

## Capabilities

### New Capabilities

- Caller-scoped, bounded Gnocchi read adapter와 Ceilometer meter normalization.
- 기존 모니터링 화면의 native 데이터 출처·상세 지표와 unavailable/fallback 표현.

### Modified Capabilities

- Instance metrics, summary, summary-batch와 project trend는 provider-specific `prometheus_available` 대신 실제 선택된 데이터의 `monitoring_available`을 사용하며 저장소 내 호출자를 함께 이행한다.
- 관리자 monitoring summary에 native 시스템 telemetry를 추가하되 기존 Nova/service inventory와 exporter reachability 의미는 보존한다.

## Impact

Backend monitoring services/APIs, frontend monitoring consumers·locales, 관련 behavioral 회귀와 API/deployment/architecture 문서에 한정한다. 새 SQL schema, 별도 telemetry DB, admin service-account fallback, infrastructure enablement, 라이브 polling agent 설치·운영 배포·릴리즈는 포함하지 않는다. 실제 HTTP collector/API와 브라우저를 합성 Keystone/Gnocchi 경계에서 검증하며 live OpenStack 수집·권한·archive policy의 운영 acceptance로 보고하지 않는다.
