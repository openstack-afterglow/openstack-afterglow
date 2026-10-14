## Implementation Tasks

- [x] 기존 calendar scheduler와 renewable Redis operation lease 패턴을 검토하고 leader/worker 분배·장애 인계 계약을 확정한다.
- [x] Redis server-time membership/leader lease, atomic balanced assignment와 current-assignment+volume-lease claim을 구현한다.
- [x] 실제 scheduler/main lifecycle을 leader-only policy scan과 assigned worker execution으로 cutover하고 기존 정책/active journal·SDK drain·force/slot/retention 의미를 유지한다.
- [x] 3-worker 균등 분배·동일 slot 단일 제출·stale owner 거부·Redis 장애·heartbeat/종료·장애 인계·unknown 미재전송 regression을 추가한다.
- [x] 실제 Redis와 독립 3개 process에서 분배·timer·leader/worker crash 인계를 실행하고 exact/named target과 source architecture guard를 검증한다.
- [x] 실제 관측 경계와 남은 위험을 API/HA deployment/architecture/changelog/testing 문서에 기록하고 OpenSpec을 archive한다.
