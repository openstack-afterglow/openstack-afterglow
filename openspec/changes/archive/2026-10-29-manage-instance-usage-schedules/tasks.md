## Implementation Tasks

- [x] 기존 생성·분산 작업·알림·볼륨 계약과 고성능 분류를 조사하고 사용자의 12 vCPU/64 GiB + 관리자 추가 지정, 기존 한 달 유예, metadata 정본 결정을 기록한다.
- [x] Native metadata 스키마·달력 한 달 기본값·GPU/12 vCPU/64 GiB/additive 분류·입력 검증을 구현한다.
- [x] 일반 sync/SSE·관리자 SSE·MCP 최초 CREATE에 필수 일정을 포함하고 preview/확정 계약을 갱신한다. MCP는 승인 날짜가 흔들리지 않도록 명시적 timezone-aware expires_at을 요구한다.
- [x] 사유·revision을 요구하는 연장 및 만료 동작 설정 API를 구현한다.
- [x] 기존 대상의 한 번만 등록하는 한 달 유예와 metadata 정본 scheduler를 구현한다. 명시 활성화 전에는 native census·등록·만료 처리 0이며 dev Compose는 false를 강제한다.
- [x] 기본 shelve→offload, 선택 stop→delete의 관측·불명확 결과·소유권/lease fencing을 구현한다.
- [x] 자동 VM 삭제 전 볼륨 기본 보존·명시 선택 삭제 flag와 단일 연결/동일 프로젝트를 검증한다. 일반/관리자 수동 attachment 변경도 같은 잠금으로 직렬화한다.
- [x] 사용자 추가 승인: Palimpsest·Union 관리형 VM도 기존 자원 기록·회수 경로를 확장해 자동 삭제와 기본 볼륨 보존을 제공한다. 증명 없는 legacy 소유권은 추정하지 않는다.
- [x] 생성 일정·검토, 관리자 추가 flavor, 상세 연장/만료 동작과 알림을 기존 UI/지역화에 통합한다.
- [x] 추가 발견된 Palimpsest catalog·관리자 consume·import consumer의 독립 생성 입력과 첫 native CREATE metadata 누락을 해소한다. 기존 SQL intent는 생성 입력 전달용일 뿐 live 일정은 native metadata만 읽는다.
- [x] 정확한 backend/frontend selector, instances target, 실제 Redis/native SDK HTTP 및 Chromium 합성 시나리오로 생성·연장·만료·데이터 보존·경합을 검증한다. 전체 frontend469files5728 및 runner9, named instances1881backend/780frontend, managed345, palimpsest518backend/268frontend, config235, 최종 지연 native-send2 passed; 중복 합산하지 않는다.
- [x] 문서·아키텍처·changelog에 계약과 실제 증거/경계를 기록하고 OpenSpec을 archive한다. 운영 배포·native writer 활성화·전체 test:gate·commit/push는 수행하지 않았다.
