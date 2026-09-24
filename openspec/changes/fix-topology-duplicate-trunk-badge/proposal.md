# 트렁크 배지 중복 제거

## 문제

캔버스 토폴로지에서 tenant 트렁크 배지가 **바로 옆 가상 스위치 카드와 같은 숫자**를 찍는다.

```
▼ 5.2M ▲ 4.3M              ← HUD 트렁크 배지 (netId 한 개)
  네트워크 합산
vSwitch-sample-private     ← 노드 카드, 약 15px 아래
  Tenant OVS Bridge ▼ 5.2M ▲ 4.3M
```

코드상 같은 값임이 증명된다.

- 배지: `fmtRate(edgeRate(e, traffic, graph))` → `trunk` 이면 `sumNetworks(t, trunkNetIds(e, graph))`
- `trunkNetIds` 는 uplink 가 아닌 트렁크에 대해 **항상** `[e.netId]` 한 개
- ⇒ `sumNetworks(t, [netId])` = `traffic.networks[netId]`
- 스위치 카드: `fmtRate(traffic?.networks?.[node.netId])` — **같은 식**

`2026-09-14-fix-topology-traffic-intensity-scale` 에서 provider uplink 배지만 접었고 tenant
배지는 남겼다. 원래 화면에는 같은 값이 세 번 있었고 그중 하나만 없앤 셈이다.

부수 문제로 배지 표시 임계(`k < 0.45`)가 카드의 `compact` LOD 경계(`k < 0.5`)와 어긋나
`[0.45, 0.5)` 구간에서는 카드의 `.node-sub` 가 통째로 숨겨진 채 배지만 떠 있었다.

## 해결

배지 게이트를 **`trunkNetIds.length < 2` 하나로 일반화**한다. 배지는 스위치 카드가 못
보여주는 것, 즉 **2개 이상 네트워크의 합**만 맡는다. uplink 전용이던 조건을 모든 트렁크에
적용하면 tenant 배지는 자동으로 전부 걸러지고, 라우터당 하나 제한(게이트웨이 + shared
provider 인터페이스가 같은 `trunkNetIds` 를 갖는 경우)만 uplink 분기에 남는다.

배지 임계를 `k < 0.5` 로 올려 카드의 `compact` 경계와 맞춘다 — "0.5 아래에서는 캔버스에
숫자가 없다" 한 줄로 설명된다.

## 잃는 것이 없음

- 값: 스위치 카드가 그대로 들고 있다.
- 트렁크 통과량 추정: 선 굵기(`switchThroughput` 중점 추정)에 그대로 남는다.
- 설명: 트렁크 선 hover title(`연결 네트워크 합산 트래픽 · 라우터 exporter 없음`)이 남는다.
- 이력: `TopologyNetworkPanel` 의 네트워크 합산 스파크라인이 남는다.

단, 값이 **항상 같은 화면 안에** 있다는 뜻은 아니다. 배지는 라우터↔스위치 중점에 놓이고
스위치 카드는 그 스위치 위치에 있으므로, 중점은 화면 안인데 카드는 바로 바깥인 pan 위치가
존재한다. 그때 값은 사라지는 것이 아니라 화면 이동을 요구한다.

실측(2026-09-13, Neutron 라우터 30개 전수)에서 tenant 망을 2개 이상 무는 라우터는 0개이므로
이 배포에서는 배지가 전혀 뜨지 않고 값은 스위치 카드에만 있다.

## 덧붙인 정리

배지가 남는 경우는 정의상 전부 uplink 이므로 `CanvasHud` 의 캡션 삼항
(`uplink ? UPLINK_* : TRUNK_*`)은 도달 불가가 된다. 삼항을 접고 `TRUNK_CAPTION`·`TRUNK_TITLE`
상수와 `HudBadgeItem.uplink` 필드를 제거해, 렌더될 수 없는 분기를 계약처럼 남기지 않는다.
범례는 실제로 보이는 유일한 캡션인 `하위망 합산` 의 뜻(그 라우터가 직접 무는 하위 네트워크들의
합)을 정의한다.
