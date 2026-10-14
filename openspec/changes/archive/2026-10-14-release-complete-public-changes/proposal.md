## Why

사용자는 남은 전체 공개 변경을 커밋하고 배포까지 완료하라고 명시 승인했다. 현재 원본 체크아웃의 dirty/index/private 설정을 보존하며 최신 origin/dev와 공개 WIP를 격리 local dev에서 통합한다. 이미 관측한 storage deletion unit11개와 database shallow-state type 오류는 최소 수정하고 필수 gate·runtime smoke·review를 통과한 source만 제출한다.

## What Changes

- Afterglow1.30.16, Lumen0.6.8, Drover0.4.15, Waygate0.3.4, Palimpsest0.3.5 patch 후보에 모든 공개 source·test·docs·dependency 변경을 최신 dev 보호와 함께 통합한다. 원래 branch/working/index·private 설정·기존 tag는 보존한다.
- Bklit 수치 시각화와 volume transfer/backup, monitoring, distributed background work, block source/consumer, private execution credential 등 현재 WIP의 계약을 source 기준으로 검토한다. 계약 완화·test skip·기능 확장은 하지 않는다.
- 최소 오류 수정 후 exact→related→전체 gate, 실제 compiled/browser/service runtime과 canonical supported-platform image를 검증하고 architecture freshness·release metadata·immutable source/ref evidence를 기록한다.
- 검증된 dev source의 일반 commit/push와 정확한 SHA CI/CD를 완료한다. CI를 통과한 commit에만 새 불변 tag를 발행하고 version image/package 및 latest/stable alias의 revision/digest를 확인한다.
- 운영 read-only baseline·native multinode parse·서비스 대상·writer/migration/IAM/storage 호환성과 recoverable backup/restore를 먼저 확인한다. /etc/kolla에서 승인된 five-service tag로 genconfig→pull→prechecks→reconfigure를 실행하고 필요한 operator package만 정확한 release로 갱신한다.
- 실제 운영 versions/readiness/auth와 cloud.dmslab.re.kr의 사용자 대시보드/Bklit surface를 확인한다. 원래 config/key/DB/volume/inventory와 비대상 container를 보존한다. 차단된 선행 조건은 정확히 보고하고 우회하지 않는다.

## Capabilities

### Modified Capabilities
- 기존 공개 기능의 검증된 dev 통합·patch 발행·운영 cutover.

## Impact

이 승인은 source commit/push/tag/publication과 다섯 서비스의 표준 Kolla 배포에 한정한다. main 직접 commit·dev→main merge·force push·운영 policy 권한 확대·과금 inference·임의 cloud/GPU resource mutation·광역 prune·volume 삭제는 하지 않는다. 배포 성공은 컨테이너 시작/과거 receipt가 아니라 exact artifact/readiness/운영 surface 검증이며, mixed-version/migration·복구 조건 미확정이면 cutover를 차단한다.
