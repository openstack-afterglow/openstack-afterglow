# topology-canvas-view

## Goal
사용자·관리자 토폴로지 페이지에 좌표 기반 캔버스 뷰를 추가해 네트워크 경계·멀티 NIC 인스턴스·per-NIC 트래픽을 한 화면에서 읽을 수 있게 한다. 기존 레인 뷰는 유지하고 토글로 고른다.

## Scope
- `frontend/src/lib/components/topology/canvas/` 신규 서브시스템: `buildGraph`(네트워크당 가상 L2 스위치, per-NIC 케이블, 트렁크, FIP, LB VIP/멤버), `autoLayout`(결정론적 티어·인접 체인·존 교차 컬럼), `viewport.svelte.ts`(팬/줌 0.35–2.2x), `TopologyCanvas.svelte`와 HUD·존·엣지·카드·툴바·범례 컴포넌트.
- 두 라우트(`/dashboard/network/topology`, `/admin/topology`)에 "레인 | 캔버스" `ToggleGroup` 추가. 기본은 캔버스, 선택은 localStorage `topology.view`.
- 수동 배치는 localStorage `topologyCanvas.layout.<user|admin>.<projectId|all>` 에 저장하고 구조 갱신 시 id 기준으로 정리한다.
- 라우터는 자신이 게이트웨이인 네트워크 존에 소속되고, 존 내부는 라우터 → 스위치 → LB → 인스턴스 → 데이터베이스 순으로 쌓인다.
- 합성 L3 코어 노드를 두지 않는다. 외부(프로바이더) 네트워크의 가상 스위치 자체가 인터넷 경계이며 구름 글리프로 표시하고, Floating IP 점선은 해당 외부망 스위치로 직접 잇는다.
- 라우터 트렁크 배지는 `traffic.networks` 네트워크 합산값이며 캡션 "네트워크 합산"으로 그 사실을 명시한다(라우터 exporter 없음).
- 백엔드는 추가 OpenStack 호출 없이 이미 가져온 SDK 객체에서 인스턴스 NIC `port_id`/`mac_addr`, `flavor_name`/`image_id`, 네트워크 `mtu`, 라우터 `enable_snat`/`routes`, 데이터베이스 인스턴스 여부(`is_database`)를 더 반환한다.
- provider network type·segmentation id·physical network 는 `AdminTopologyNetwork`/`AdminTopologyData` 에만 두어 사용자 응답에는 키 자체가 없다.
- 사용자 토폴로지 응답의 `floating_ips` 를 조회 단계와 응답 단계 모두 현재 프로젝트 소유분으로 제한하고, 조회 중 `HTTPException` 은 원래 상태 코드로 전달한다.
- 토큰(`--color-topology-gateway`, `--color-topology-internal-2`, `--topology-zone-fill-alpha(-active)`, `--color-topology-grid-minor/major`)과 `STATUS_STYLES` 의 DEGRADED/OFFLINE/NO_MONITOR/DOWN 을 먼저 정의한 뒤 feature 를 구성한다.

## Non-goals
- 레인 뷰 제거, 미니맵, 물리 시뮬레이션 레이아웃, 캔버스에서의 변경 액션(전원·attach 등). 상세는 읽기 전용이다.
- 라우터 자체 트래픽 exporter 도입.
- 배치의 서버 측 영속화.
