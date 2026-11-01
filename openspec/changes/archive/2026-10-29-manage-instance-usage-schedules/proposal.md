## Why

GPU 및 고성능 CPU 인스턴스의 장기 점유를 사용자가 명시한 일정으로 관리한다. 사용 종료·연장을 사전에 안내하고, 연장하지 않은 작업은 기본 보관(shelve/offload)하여 compute를 반환한다. 사용자의 명시적 선택에만 VM 및 연결 볼륨을 제거한다.

## What Changes

- GPU 전체, CPU 12 vCPU 이상 또는 RAM 65536 MiB 이상과 관리자가 extra spec `afterglow:usage_schedule_required=true`로 추가 지정한 flavor를 대상으로 한다. 기본 대상은 false 지정으로 제외할 수 없다.
- 신규 생성은 사용 일정을 필수 입력한다. 기본 종료일은 생성 시점부터 달력 한 달(월말 보정)이며 기본 만료 동작은 shelve이다. 한 달을 넘기는 초기 요청과 사용 기간 연장은 사유를 기록한다.
- 기존 대상도 최초 성공적인 metadata 등록 시점부터 달력 한 달의 유예를 받는다. 기존 생성 시각으로 소급해 즉시 만료시키지 않는다.
- **일정·revision·최신 연장 사유·처리 상태는 Nova 인스턴스 metadata가 유일한 정본이다.** 별도 SQL/Redis 일정 저장소나 DB migration을 도입하지 않는다. Redis는 cloud/project/server별 임시 실행 잠금·작업 분배에만 사용한다.
- 사용자·관리자·MCP 생성 경로 모두 첫 Nova CREATE에 metadata를 포함한다. 일정을 누락하거나 API를 우회한 기존 native 인스턴스는 백그라운드 census에서 정책에 맞게 최초 등록한다.
- 프로젝트 알림 및 인스턴스 상세에 만료 7일 전부터 정리/연장 안내를 제공하고 3일·1일 전 및 만료/처리 오류를 구분한다. 연장은 사유와 revision을 요구하며 자동 unshelve는 하지 않는다.
- 만료 시 기본 shelve를 요청하고 실제 SHELVED 뒤 offload, SHELVED_OFFLOADED 관측 이후에만 자원 반환 완료로 표시한다. 선택한 자동 삭제는 정지 관측 후 일반 삭제한다.
- 자동 삭제는 기본적으로 root/data Cinder 볼륨의 native delete_on_termination=false를 검증한다. 명시적 연결 볼륨 삭제 동의가 있으면 정확한 프로젝트·단일 연결 볼륨의 flag를 검증/설정한다. 소유권·공유 여부·flag가 불명확하면 VM 삭제를 차단한다. snapshot/backup/Manila 등 다른 자원은 삭제하지 않는다.
- API 연장/설정 변경과 scheduler의 단일 임시 잠금, fresh native 소유권/metadata readback, 영속 metadata dispatch marker로 경합을 제어한다. 불명확한 native POST/DELETE는 자동 재실행·강제 처리하지 않는다.

## Capabilities

- Native metadata는 해당 프로젝트의 Nova metadata 수정 권한으로 직접 변경할 수 있다. 이 기능은 Afterglow 경유 입력·사유·revision 검증과 관리형 자동 처리이며 native CLI 사용자를 강제로 통제하는 정책이 아니다. 직접 날짜 변경은 API 사유 검증을 우회하고 모든 일정 key 삭제는 새 유예 등록을 유발할 수 있다. 부분/손상 metadata는 오류로 표시하고 삭제 근거로 쓰지 않는다. 별도 서명키/DB 정본이나 Nova policy 변경은 이번 요청에 추가하지 않는다.
### New Capabilities

- Metadata 기반 인스턴스 사용 기간·연장·만료 처리·기존 인스턴스 유예.
- 사용자 선택 자동 정지/삭제 및 볼륨 보존/삭제 동의.
- 일정 입력·상세 관리·만료 알림과 관리자 추가 flavor 지정.

### Modified Capabilities

- 일반/관리자/MCP VM 생성 입력 및 최초 Nova metadata.
- 기존 WorkDispatcher 기반 백그라운드 작업과 공용 dashboard/instance UI.

## Impact

- Backend models/routes/services/main, frontend wizard/detail/flavor/notifications/i18n 및 관련 API/사용자/보안/운영 문서.
- 신규 endpoint pytest와 일정/경합/볼륨/불명확 응답 regression; native SDK HTTP 및 실제 Chromium smoke로 검증한다.
- DB migration, 운영 배포, 실제 cloud 인스턴스/볼륨 변경은 이번 소스 구현에 포함하지 않는다. 합성 native/API와 실제 운영 수용 증거는 분리한다.
