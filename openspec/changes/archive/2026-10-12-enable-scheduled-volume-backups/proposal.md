## Why

사용자는 기존에 요청한 볼륨 자동 백업을 어디서 설정하는지 찾을 수 없다. 현재 source는 desktop 전용 작은 목록 토글에서 기본 보존 값만 저장하고, API가 첫 사이클을 즉시 실행한 뒤 main의 1시간 루프가 마지막 생성 시각의 경과를 검사한다. 실행 시각·시간대·예정 시각·실행 결과는 노출하지 않으며, 연결 중 볼륨은 force=false로 Cinder에서 실패한다. 기존 사이클은 보존 0인 tier도 생성하고 완료 전 새 항목을 가정해 오래된 백업을 정리한다.

## What Changes

- 기존 `/dashboard/volumes/backups`에 명시적 자동 백업 설정 버튼과 정책 관리 영역을 추가한다. 목록/공용 상세 작업 메뉴와 desktop의 불투명 즉시 토글도 같은 설정 진입점으로 통일한다. Mobile/tablet에서도 동일한 설정·수정·중지와 결과를 제공한다.
- 기존 Redis per-volume 정책과 max_daily/max_weekly/max_monthly를 유지하고 활성 상태, HH:mm 실행 시각, IANA 시간대, 월요일=0의 주간 요일(0–6), 월간 실행일(1–28), 별도 force 동의를 저장한다. 0 보존은 해당 주기를 미실행한다. 새 정책은 다음 예정 시각부터 실행하며 저장 직후 무조건 3개를 만드는 경로를 제거한다.
- APScheduler CronTrigger(기존 의존성)의 calendar schedule을 사용한다. 동시 due인 daily/weekly/monthly는 가장 긴 보존 tier(monthly > weekly > daily)의 단일 full backup으로 통합한다. 독립 복원/안전한 보존을 위해 새 자동 백업은 full로 만든다. 기존 백업은 삭제하지 않고 보존 범위를 안전하게 식별한다.
- GET/POST/DELETE 정책 API는 프로젝트 경계, fresh 원본 소유권과 mutation write authority를 확인한다. 활성 in-use 정책은 명시적 force를 필요로 한다. force는 정책 예약 실행 전체에만 적용하며 수동 동의를 승계하지 않고 정합성·복원을 보장하지 않는다.
- main의 실제 startup worker를 calendar due dispatcher로 연결한다. 모든 replica는 갱신 가능한 Redis per-volume lease와 durable slot claim 아래 실행하며 정책 변경/중지와 lease 손실을 mutation 전에 fence한다. 새 백업 접수/creating과 available/실패/unknown을 구분하고 다음 예정 시각·최근 실행·backup ID·안전한 오류를 조회 응답에 노출한다.
- 보존 정리는 같은 원본/프로젝트의 관리 대상이며 상태 available이고 의존성이 없는 오래된 백업만 한다. Pending/failed 신규 백업을 완성본으로 세지 않으며 수동/다른 원본/프로젝트 백업, incremental dependencies와 마지막 복구 지점을 삭제하지 않는다.
- 기존 Redis 정책은 source cutover 때 기존 활성/보존을 유지한 새 calendar 필드의 explicit normalization으로 수렴한다(기존 UTC 기준·03:00, 월요일·매월 1일, force=false). Legacy 실행기/즉시 토글/명칭-문구 테스트의 병행 shim을 두지 않는다.

## Capabilities

### New Capabilities

- 실행 시각·시간대와 일/주/월 보존 주기를 선택하는 볼륨 자동 백업 관리.
- 실제 due 실행, HA 중복 억제, 비동기 상태 관측과 안전한 완료본 보존.

### Modified Capabilities

- 기존 자동 백업 API와 Redis 정책, in-process backup worker 및 볼륨 작업 메뉴.
- 기존 수동 force는 유지하며 자동 정책에 별도 명시 동의를 부여한다.

## Impact

Backend owns `backend/app/services/auto_backup.py`, `backend/app/api/storage/volume_backups.py`, backup startup/shutdown in `backend/app/main.py`, necessary native backup projection fields in `backend/app/services/cinder.py`, and affected backend regression tests. Frontend owns volume backup route/composition/types/controller/menu and four volume catalogs plus consumer UI regressions. Integration owner updates docs/API/public localized guides, ARCHITECTURE/DESIGN/CHANGELOG, registry and scoped receipts after actual smoke.

No new database table, service, package, global operator configuration, production deployment or live Cinder/volume/VM mutation is authorized by this change. Reuse existing Redis/Cinder/APScheduler and UI primitives. Preserve concurrent WIP, user private configuration and shared index/review marker. Exact/local native and browser evidence must not be presented as live IAM, backup storage or guest restore qualification.
