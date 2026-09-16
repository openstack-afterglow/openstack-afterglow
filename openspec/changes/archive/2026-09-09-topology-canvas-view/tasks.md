## Implementation Tasks

- [x] Backend: Pydantic 모델 확장(`TopologyNetwork.mtu`, `TopologyRouter.enable_snat/routes`, `TopologyInstance.flavor_name/image_id`, `AdminTopologyNetwork`/`AdminTopologyData`)
- [x] Backend: `neutron.get_topology(include_provider)`에서 mtu/enable_snat/routes/provider 채우기, compute 포트 인덱스 헬퍼 추출
- [x] Backend: `networks.py`/`admin.py` 핸들러에서 `ip_addresses[].port_id/mac_addr/network_id`, flavor_name/image_id 조인; admin은 `AdminTopologyData` 응답
- [x] Backend tests: `test_topology.py`, `test_admin_filters.py`, `test_neutron.py` 확장 (사용자 응답에 provider 키 없음 포함)
- [x] Docs: `docs/api/networks.md`(+en) §6, `docs/api/admin.md` 필드 표·샘플 갱신
- [x] Tokens: `layout.css`(dark/light) + `tokens.ts` 확장, `designSystemRules.test.ts` 토큰 목록, DESIGN.md 예외/motion exception, `STATUS_STYLES` 확장
- [x] Frontend types: `$lib/types/topology.ts` 확장, `components/topology/types.ts`가 wire 타입을 재수출
- [x] Frontend canvas: `canvas/topologyGraph.ts`, `topologyLayout.ts`, `layoutStorage.ts`, `viewport.svelte.ts`, `TopologyCanvas.svelte` + 하위 컴포넌트, `TopologyNetworkPanel.svelte`, `CanvasLegend.svelte`
- [x] Frontend routes: 두 토폴로지 라우트에 뷰 토글(기본 캔버스, localStorage), 네트워크 패널 연결, 튜토리얼 selector 유지
- [x] Mockup fixture 갱신 + `contracts.test.ts`/`transport.test.ts` 통과
- [x] Vitest: graph/layout/storage 순수 함수 테스트, TopologyCanvas 렌더/선택/intent 테스트, `page.intent.test.ts` 갱신
- [x] `npm run check`(svelte-check) 오류·a11y 경고 0, `npm run test:frontend:design` 통과
- [x] ARCHITECTURE.md Code map/Runtime flows 갱신 + stamp, CHANGELOG.md, 튜토리얼 문구
- [x] `npm run test:gate` 통과 후 변경 파일 목록 보고 (커밋 보류)
