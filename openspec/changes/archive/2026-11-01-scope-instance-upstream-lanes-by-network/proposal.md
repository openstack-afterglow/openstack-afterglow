## Why
인스턴스의 상위 fanout 순번과 자동 여백이 다른 네트워크 연결까지 합산해 무관한 망의 높낮이를 바꾼다.

## What Changes
- 스위치의 전체 연결 기반 fanout은 유지한다.
- 인스턴스 TOP cable lane은 동일 netId 연결만 순번·개수를 계산한다.
- 자동 여백에서 VM peer fanout도 해당 netId만 사용한다.
- NIC 접점·stableOrder·HUD 회피와 traffic 의미는 유지한다.

## Impact
Frontend topology geometry only. No API, schema, configuration, service or deployment changes.
