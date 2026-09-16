# 토폴로지 응답 지연 제거와 패킷 흐름 기본 활성화

## 문제

운영(DMSLab)에서 `GET /api/v1/networks/topology`가 8~10초 걸린다. 백엔드 request 로그 기준
`duration_ms` 8286~9939. 원인은 핸들러가 서로 의존하지 않는 OpenStack 조회를 직렬로 수행하고,
포트 조회가 필요 이상으로 큰 응답을 받기 때문이다. 운영 컨테이너 실측(admin scope):

| 호출 | 시간 |
|---|---|
| `neutron.get_topology` | 4267 ms |
| `build_compute_port_index` (전체 포트 350개) | 2530 ms |
| `list_floating_ips` (전체 포트 + 전체 서버 detail) | 3167 ms |
| 핸들러 직렬 fan-out 합계 | 8938 ms |

또한 캔버스 패킷 흐름 시뮬레이션이 옵트인이라 기본 화면에서 트래픽 흐름이 보이지 않는다.

## 변경

- `app/services/parallel.py`의 `run_parallel`로 독립 조회를 동시에 실행한다.
  - `neutron.get_topology`: 네트워크·서브넷·라우터·Floating IP·라우터 인터페이스 포트
  - `/api/v1/networks/topology`, `/api/v1/admin/topology` 핸들러: topology·포트 인덱스·Trove IP·Nova 서버
- `build_compute_port_index`는 실제로 읽는 속성만 `fields`로 요청한다(`device_owner` prefix 매칭이
  필요하므로 서버측 `device_owner` 필터는 쓰지 않는다).
- `list_floating_ips`는 FIP가 붙은 포트만 `id` 필터로 조회하고, 인스턴스 이름은 detail 없는
  Nova 목록에서 읽는다.
- 캔버스 패킷 흐름을 기본 on으로 바꾼다. `prefers-reduced-motion` 하드 off 계약은 유지한다.

## 비목표

- cache TTL·폴링 주기 변경
- `/topology/traffic`(Prometheus 경로) 최적화
- 응답 스키마 변경
