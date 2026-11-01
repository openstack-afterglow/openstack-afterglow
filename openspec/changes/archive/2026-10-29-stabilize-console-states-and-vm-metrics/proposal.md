## Why

사용자 실제 localhost:3080 화면에서 dashboard의 loading→loaded 구조 변화, chart/table의 present/empty/error 시각 격차, VM metrics에 compute node_exporter 노출, 전역 sidebar VM 생성 CTA와 모든 서비스 탐색 제어, backup glyph 문제를 보고했다. 인증 지연·실패·503도 반복 관측했다. 이전 정보 위계 개선의 정상 스냅샷 검증은 상태 전환과 실제 인증 경로의 검증을 대체하지 않는다.

## What Changes

- Dashboard와 관련 chart/table은 같은 제목·도구·그리드·표면을 상태 간 유지하고 내용만 교체한다. Missing/failed를0이나 빈 성공으로 바꾸지 않는다.
- 사용자 VM metrics를 current-project Nova UUID-owned instance metrics 경로로 연결한다. Compute host node_exporter는 admin infrastructure이며 VM fallback이 아니다.
- Sidebar/drawer 전역 VM 생성 CTA를 제거하고 instance 페이지의 기존 생성·tutorial 경로를 유지한다.
- 모든 서비스는 상위 탐색 제어로 정리하고 volume/database backup glyph를 수정한다.
- 실제 인증/503의 provider·cache·refresh·scope 원인을 로그/런타임으로 구분한다. 원인 확인 없는 retry/cache TTL/권한 완화는 하지 않는다.

## Constraints

기존 dev shared tree·사용자 동시변경·index를 보존한다. Native authority, private generation/ABA fence, fail-closed, token/secret lifetime과 mutation no-replay를 보존한다. 실제 cloud resource/IAM mutation·배포·commit/push는 범위 밖이다. 인증 사용자 브라우저는 가능한 읽기 관측만 사용하며 credential 값을 기록하지 않는다. 불가능한 live 증거는 synthetic과 구별한다.

## Completion

각 사용자 항목을 checklist로 추적한다. 실제 source 화면에서 loading/ready/mixed/empty/error와 두 테마·반응형·탐색·인스턴스 metrics 범위를 실행한다. 인증 결함은 확인된 root cause와 fail-before/pass-after 또는 실제 runtime evidence를 남긴다. 영향 docs/architecture/changelog와 exact verification receipt를 갱신하고 repository rapid archive 흐름을 따른다.
