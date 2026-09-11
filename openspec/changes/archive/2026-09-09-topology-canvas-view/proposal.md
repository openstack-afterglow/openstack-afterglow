## Why

기존 네트워크 토폴로지(`GlobalTopology.svelte`)는 좌표 모델이 없는 레인 레이아웃이라 멀티 NIC 인스턴스의 소속, 라우터의 경계 위치, 네트워크 단위 트래픽을 한눈에 읽기 어렵다. 2026-09-08 Artifact 목업("Afterglow Topology Canvas")으로 캔버스형 재설계(네트워크당 가상 L2 스위치, 경계 밴드 라우터, 멀티 NIC 인스턴스의 존 교차 배치, 드래그 시 실시간 존 재계산, 팬/줌, 검색 하이라이트, 읽기 전용 인스펙터)를 검토했고, 이를 저장소에 옵트아웃 가능한 기본 뷰로 반영한다.

사용자 결정: 라우터 트렁크 트래픽은 `traffic.networks` 네트워크 합산값으로 표시하고 라벨에 명시한다. VLAN/provider 메타는 관리자 응답·화면에서만 다룬다. 기존 레인 뷰는 삭제하지 않고 토글 뒤에 유지한다. 수동 배치 위치는 브라우저 localStorage에 사용자+프로젝트별로 저장한다.

## What Changes

- Backend: `GET /api/v1/networks/topology`와 `GET /api/v1/admin/topology` 응답에 추가 호출 없이 얻을 수 있는 필드를 추가한다.
  - `TopologyNetwork.mtu`
  - `TopologyRouter.enable_snat`, `TopologyRouter.routes[{destination, nexthop}]`
  - `TopologyInstance.flavor_name`, `TopologyInstance.image_id`, `ip_addresses[].port_id`, `ip_addresses[].mac_addr` (Neutron compute 포트에서 조인)
  - 관리자 응답 전용 `AdminTopologyNetwork.provider_network_type / provider_segmentation_id / provider_physical_network` (`AdminTopologyData`). 사용자 응답에는 해당 키를 포함하지 않는다.
  - 두 핸들러가 공유하는 compute 포트 인덱스 헬퍼를 `neutron.py`로 추출한다.
- 보안 리뷰 반영: 사용자 토폴로지 응답의 `floating_ips`를 프로젝트 소유분으로 제한(조회 단계 `project_id` 전달 + 응답 단계 fail-closed 필터)하고, 토폴로지 핸들러에서 `HTTPException`을 그대로 전달한다.
- Design tokens: `layout.css`(dark+`:root.light`)와 `tokens.ts`에 `--color-topology-gateway`, `--color-topology-internal-2`, `--topology-zone-fill-alpha`(+`-active`), `--color-topology-grid-minor`, `--color-topology-grid-major`를 추가하고 DESIGN.md의 topology 도메인 색 예외와 named motion exception(패킷 흐름 시뮬레이션: 옵트인·기본 off·reduced-motion 하드 off)을 갱신한다. `STATUS_STYLES`에 `DEGRADED`, `OFFLINE`, `NO_MONITOR`, `DOWN`을 추가한다.
- Frontend: `frontend/src/lib/components/topology/canvas/`에 순수 모듈(`topologyGraph.ts`, `topologyLayout.ts`, `layoutStorage.ts`, `viewport.svelte.ts`)과 `TopologyCanvas.svelte` 컴포넌트를 추가한다. `dashboard/network/topology`, `admin/topology` 두 라우트에 `ToggleGroup` "레인 | 캔버스"를 추가하고 기본값은 캔버스, 선택은 localStorage `topology.view`에 저장한다. 레인 뷰(`GlobalTopology`)와 튜토리얼 selector, 150ms intent prefetch 계약은 유지한다. 스위치/네트워크 선택 시 읽기 전용 `TopologyNetworkPanel`을 SlidePanel로 연다.
- Mockup fixture: `mockup/state.ts` 토폴로지에 `network_id`/`port_id`/`mac_addr`, 멀티 NIC 인스턴스, `traffic.interfaces`, `routers: {}` + `_meta.router_traffic`를 반영한다.
- Docs: `docs/api/networks.md`(+en) §6, `docs/api/admin.md`, `ARCHITECTURE.md`(Code map + stamp), `CHANGELOG.md`, 튜토리얼 step 문구.

## Capabilities

### New Capabilities
- 캔버스형 토폴로지 뷰(팬/줌/드래그, 존 실시간 재계산, per-NIC 케이블, 트렁크 네트워크 합산 배지, 검색 하이라이트, 패킷 흐름 시뮬레이션 옵트인, 배치 localStorage 저장)
- 토폴로지 응답의 per-NIC port_id/MAC, flavor, MTU, SNAT, 정적 경로 (관리자 응답은 provider 세그먼트 포함)

### Modified Capabilities
- 토폴로지 페이지에 뷰 토글 추가(기본 캔버스, 레인 유지)
- `STATUS_STYLES` 확장(Octavia 운영 상태, 라우터 DOWN)

## Impact

- API: 필드 추가만 있고 기존 필드·캐시 키·권한 규칙은 변경하지 않는다. provider 메타는 admin 모델에만 존재한다.
- Frontend: 새 파일은 raw hex/palette 클래스 없이 토큰만 사용한다(visualDebt 가드). `page.intent.test.ts`는 두 뷰 모두에서 intent 계약을 검증하도록 갱신한다. 튜토리얼 `admin-network-*` selector 6개는 두 뷰에서 모두 존재한다.
- 검증: 관련 pytest/vitest selector → `npm run test:frontend:design` → `npm run test:gate`. 커밋은 보류(사용자 지시).
