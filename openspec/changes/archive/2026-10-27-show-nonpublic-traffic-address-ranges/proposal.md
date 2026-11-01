## Why

국가 미확인 XX와 origin unknown에 사설 관리망/VPN 관측이 섞이지만 현재 저장소는 검증한 원본 주소를 국가/origin/HMAC으로만 집계한다. 사설·비국가 주소 대역별 관측을 표시해야 국가 트래픽과 구분할 수 있다.

## What Changes

- 기존 주소 provenance/XFF fail-closed와 cluster_cidrs origin 정책을 그대로 유지한다. 임의 사설 주소를 cluster internal 또는 VPN으로 추정하지 않는다.
- 검증한 비global/멀티캐스트 주소에만 bounded network 차원을 추가한다. 원본 출발지가 확인되면 `basis=resolved_client`, XFF 누락/오류/all-trusted로 원본이 불명이어도 검증한 socket 상대가 비국가 주소라면 `basis=socket_peer`로 별도 표시한다. 후자는 원래 출발지·origin·국가를 확인한 증거가 아니다. 미검증/잘못된 peer·XFF 추측은 금지한다.
- RFC1918 IPv4는 /16 집계(실제 subnet 발견 아님), 기타 주소는 표준 특수 목적 대역으로 묶고 raw host IP를 보존하지 않는다. IPv6는 ULA/link-local/loopback/기타 표준 범위로 한정한다.
- snapshot에 networks: [{network,kind,basis,...TrafficMetrics}]를 추가한다. kind는 private/shared/loopback/link_local/documentation/benchmark/multicast/reserved/unspecified. origin/source/range 필터·dedupe·TTL을 공유하고 국가 XX는 기존 합계를 유지한다. Network 행은 XX의 부분 집계이지 추가 요청이 아니다.
- 국가 순위 아래 별도 비국가 IP 대역 표/compact card에 대역, 종류, 출발지/연결 상대 근거, 요청, 오류를 표시한다. IPv4 /16 집계와 관리망/VPN 비추정, 과거·주소 불명은 복원 불가를 명시한다. 기존 UI primitives와 모든 지원 locale을 유지한다.

## Capabilities

### New Capabilities
- 검증된 비국가 출발지의 privacy-preserving 대역별 관측.

### Modified Capabilities
- 관리자 traffic snapshot additive networks 계약 및 responsive 표시.

## Impact

SQL/schema/설정/의존성/배포 변경 없음. Redis hourly hash의 bounded additive 차원만 추가하며 기존 bucket은 소급 분류하지 않는다. 개인정보 원본 IP 미저장, 기존 origin 인가/분류 및 proxy 신뢰 경계 유지. source-only; 운영 변경/commit/push 없음.
