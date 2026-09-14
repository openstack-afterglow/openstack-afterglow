# Tasks

- [x] `topologyHelpers.ts`: 하한/구간 상수화, `bpsDecade`·`edgeIntensity`·`flowRate` 재보정, `NO_TELEMETRY_STYLE` 분리
- [x] `topologyGraph.ts`: 트렁크 스칼라 `switchThroughput`(구간 중점)·`trunkIntensityBps`(망별 합산), 트렁크 굵기 하한 제거, `FLOW_MIN_BPS` 1e4, `flowStreams` 동일 스칼라
- [x] `TopologyCanvas.svelte`: uplink 배지를 `trunkNetIds().length >= 2` 로 게이트
- [x] `topologyDerivedController.svelte.ts`: 레인 뷰 null/0 구분
- [x] `CanvasLegend.svelte`: 배지·강도 문구 갱신
- [x] 회귀 테스트: 스케일 앵커, null≠조용함, 트렁크 스칼라, uplink 배지 게이트
- [x] 독립 리뷰(워크플로 4개 관점 + 지적별 적대적 검증, 36 에이전트) — 확정 20건 전부 반영
- [x] 회귀 보강: 트렁크 추정기 구간 증명, uplink 망별 합산, 흐름 예산 배정, NaN 가드, 레인 뷰 테스트 신설
- [x] 돌연변이 검사 10건 전부 테스트 실패 확인(공허한 단정 0건)
- [x] 문서: `CHANGELOG.md`, `ARCHITECTURE.md` 본문, `DESIGN.md`
- [x] `ARCHITECTURE.md` working/staged stamp — 별도 dev shipment snapshot에서 동일 fingerprint `f6f83bfdbff876dee5c33c3230f7f99d6f152e39c8242475232c9370900bc546` 검증
- [x] `npm run test:gate` 통과; 검증된 전체 shipment commit에 포함
