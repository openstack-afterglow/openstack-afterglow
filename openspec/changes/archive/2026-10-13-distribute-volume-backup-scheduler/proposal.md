## Why

각 controller/backend process가 현재 `scheduler_tick`에서 모든 calendar 정책을 조회한다. 기존 renewable volume lease와 durable slot journal은 중복 Cinder 제출을 방지하지만 정책 스캔과 실행 담당은 분배하지 않는다. 3개 controller가 공유 Redis를 사용하면서 한 곳에서 스케줄을 관리하고 살아 있는 process들에 실행/상태 확인을 분배해야 한다.

## What Changes

- 공유 Redis server time 기반 45초 worker membership/leader lease와 10초 heartbeat로 scheduler leader 하나를 선출한다. Host/PID/random incarnation으로 process identity를 자동 생성하며 controller별 수동 설정을 추가하지 않는다.
- leader만 기존 authoritative policy/active registry를 스캔한다. 새 due/active member와 소유자가 사라진 작업은 현재 살아 있는 worker의 배정 개수 기준으로 균등 배정한다(동률은 정렬된 worker 순서). 후속 scan은 정상 소유자의 pending/active 배정을 보존하여 빠른 worker가 늦게 polling하는 peer의 제출을 가져가지 않는다. 배정 map과 worker별 ready sets는 leader token을 확인하는 한 Redis Lua transaction으로 교체한다.
- worker는 자기 ready set에서만 실행을 가져간다. Live membership, 최신 assignment와 renewable volume lease의 NX acquire를 하나의 Redis Lua에서 확인한다. Batch는 현재 ready 크기까지 제한하고 기존 full-backup/force/slot/revision/unknown/retention fences를 유지한다.
- Heartbeat와 leader scheduling loop는 SDK factory/작업이 진행되는 동안에도 독립적으로 유지하여 leader가 실행 때문에 새 예약을 놓치지 않는다. 정상 종료는 두 loop를 한 번씩 cancel하고 SDK drain/close와 volume lease release 후 worker/leader 소유권을 회수한다. 장애 후 membership/leader expiry와 다음 15초 poll에서 재배정하며, hard crash 뒤 기존 90초 volume lease가 남으면 만료까지 기다린다.
- Stale leader의 배정, stale worker의 claim 및 Redis coordination 장애는 fail closed한다. Due/active 정본은 기존 정책/journal이므로 ready queue를 잃거나 담당이 죽어도 다음 leader scan으로 복구한다. Unknown provider acceptance는 재제출하지 않는다.
- Native SDK/loopback consumer에서 provider가 접수 후 응답을 잃으면 implicit connection retry로 두 개의 백업이 만들어지는 경계를 재현했다. 공유 Cinder backup 생성 helper는 기존 layer allocation의 scoped Proxy-copy/request override 패턴으로 해당 POST의 transport/status retries만 0으로 고정한다. Caller session·조회 retry·API 입력은 바꾸지 않으며 scheduled unknown은 기존 정본으로 관측한다.

## Capabilities

### New Capabilities

- 단일 HA scheduling leader와 균등한 multi-controller execution/reconciliation assignment.
- Controller/process 장애·재시작·membership 변경 후 자동 인계.

### Modified Capabilities

- 기존 calendar volume backup dispatcher의 무분배 전체 스캔을 leader scan + assigned workers로 교체한다. API/UI/policy schema, manual backup와 기존 backup 보존 의미는 그대로다.

## Impact

Backend coordinator, `auto_backup` lifecycle/dispatcher, main task startup와 behavior regressions를 변경한다. 기존 Redis를 재사용하며 DB/table/package/config/service/production에는 변경을 하지 않는다. 상세 API/deployment/architecture와 검증 기록을 갱신한다. 완료 기준은 real Redis와 독립 3개 process에서 단일 authoritative scan/동일 slot 한 제출/여러 worker 실행/leader 및 worker crash 인계/unknown 미재전송을 실제 관측하고 관련 target을 통과하는 것이다. 로컬 synthetic Cinder/identity proof를 운영 backup storage·복원·배포로 보고하지 않는다.
