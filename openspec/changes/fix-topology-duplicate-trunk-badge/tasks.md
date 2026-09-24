# 작업

- [x] 중복 확인 — 실렌더 DOM 에서 배지 `▼ 5.2M ▲ 4.3M 네트워크 합산` 과 스위치 카드
      `vSwitch-sample-private Tenant OVS Bridge ▼ 5.2M ▲ 4.3M` 이 같은 값임을 확인
- [x] 코드로 동치 증명 — `trunkNetIds` 가 non-uplink 트렁크에 `[e.netId]` 를 반환 →
      `sumNetworks(t, [netId])` = `traffic.networks[netId]` = 스위치 카드 식
- [x] `TopologyCanvas.svelte` `hudBadges` — `trunkNetIds.length < 2` 게이트를
      `isUplinkTrunk` 분기 **밖으로** 올려 모든 트렁크에 적용
- [x] `TopologyCanvas.svelte` `badgesHidden` — `k < 0.45` → `k < 0.5` (카드 `compact` 경계와 정렬)
- [x] `CanvasLegend.svelte` — 두 변종을 설명하던 줄을 한 규칙으로 축약
- [x] `TopologyCanvas.test.ts` — 배지 개수 4 → 1, tenant 배지 부재 + **스위치 카드가 값을
      들고 있음**을 함께 단정(회귀 가드 유지). 라우터당 1개 dedup·하위망 0개 테스트는 그대로 통과
- [x] `ARCHITECTURE.md` 산문 — 배지 규칙 일반화와 LOD 정렬 반영
- [x] `DESIGN.md` — 트렁크 배지 계약 문장 갱신
- [x] `CHANGELOG.md` — `[Unreleased] › Fixed` 항목 추가(1.23.0 구간은 건드리지 않음)
## 독립 리뷰 반영 (CRITICAL 0 / HIGH 0 / MEDIUM 3 / LOW 4, 판정 COMMENT)

- [x] MEDIUM — 도달 불가 캡션 분기 제거. 배지가 남는 경우는 정의상 전부 uplink 이므로
      `CanvasHud` 삼항 3곳을 접고 `TRUNK_CAPTION`·`TRUNK_TITLE` 상수와
      `HudBadgeItem.uplink` 필드를 제거했다
- [x] MEDIUM — `ARCHITECTURE.md`·`DESIGN.md` 의 자기모순 문장 제거(캡션 두 종류를 구분한다고
      써 두고 바로 뒤에서 tenant 는 배지를 안 그린다고 하던 부분)
- [x] MEDIUM — 범례에 `하위망 합산` 용어 정의 복원(언제 뜨는지만 말하고 무엇을 합치는지 빠져 있었다)
- [x] MEDIUM — 임계 회귀 테스트 추가. 값(`0.5`)이 아니라 **`[data-badges]` 와 `[data-lod]` 의
      일치**를 배율을 낮춰 가며 단정하고, 두 상태를 다 관찰했는지도 함께 검사해 공허하지 않게 했다
- [x] LOW — `badgesHidden` 주석의 근거 정정(남은 배지는 중복이 아니라 가독성 때문에 접는다)
- [x] LOW — "0.5 아래에서는 숫자가 전혀 없다" → "**트래픽 숫자**가 없다"(존 라벨 CIDR·VLAN·MTU 는 HUD 라 남는다)
- [x] LOW — 게이트 주석에서 접는 근거(중복)와 별개 기존 결함(중점 겹침)을 분리
- [x] LOW — 테스트에 `하위망 합산` 캡션 단정 복원
- [x] LOW — `proposal.md` 의 "잃는 것이 없음" 에 pan 의존성 단서 추가

## 검증

- [x] `npm run test:target -- frontend:src/lib/components/topology` — 12 파일 **203** 테스트 통과
- [x] `svelte-check` — 0 errors / 0 warnings
- [x] `npm run test:frontend:design` — 22 파일 109 테스트 통과
- [x] **돌연변이 2건 모두 죽음** — 게이트를 `isUplinkTrunk` 안으로 되돌리면 배지 테스트 2건 실패,
      임계를 `0.45` 로 되돌리면 임계 테스트가 `k=0.472` 에서 실패(문제 구간을 그대로 짚는다).
      파일은 바이트 동일하게 복원 확인
- [x] 실렌더 재확인 — 배지 0개, 스위치 카드가 값 보유, 범례 갱신, 앱 콘솔 오류 0건, 375px 모바일 정상
- [ ] `npm run test:gate` 통과 후 커밋 — **차단됨**: 같은 워킹트리에 다른 세션(cloud-shell)의
      미커밋 변경 109개가 있어 `docs:check`(working tree 해시)와 `--staged`(인덱스 해시)를
      동시에 만족시킬 수 없다. `ARCHITECTURE.md` 에는 이미 그 세션의 staged hunk 3개가 있고,
      `CHANGELOG.md` 의 새 항목도 그 세션이 만든 `### Fixed` 블록 안에 들어가 훅 단위 staging 이 필요하다.
