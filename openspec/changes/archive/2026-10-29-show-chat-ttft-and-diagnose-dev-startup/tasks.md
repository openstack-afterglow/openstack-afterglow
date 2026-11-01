## Implementation Tasks

- [x] 채팅 요청·스트림·render 소유권을 확인하고 TTFT 측정 및 표시를 구현한다.
- [x] 지원 언어와 취소·실패·재생성·thread 전환·과거 메시지 경계를 반영한다.
- [x] 네 Compose migration/bootstrap의 기존 실패 로그와 effective DB 설정으로 원인을 확인하고, 증명된 source 결함이 있으면 수정한다. 네 작업 모두 외부 MariaDB1047이며 다섯 실제 DB 목적지의 read-only WSREP 상태는 ready/connected OFF·Disconnected·Initialized다. Source 결함은 확인되지 않아 설정/DB를 변경하지 않는다.
- [x] 관련 selector와 실제 지연 SSE 브라우저 화면으로 TTFT 동작을 검증한다. 집중5files82tests 통과; 최종 compiled HTTP fixture에서 submission400ms+text1200ms→TTFT1.61초 고정, completed-only·취소·실패·재시도·재생성·과거 기록 및9언어×2theme×3viewport54조건을 검증했다. 실제 provider는 호출하지 않았다.
- [x] 영향을 받는 frontend 이미지의 지원 architecture 빌드·실행을 검증하고, 기존 Compose 실행 차단 조건과 안전한 적용 가능 범위를 보고한다. arm64 정본 frontend-only build/up 및 amd64 이미지 build/runtime health200. 원래 env/mount/port/key와 비대상 container는 보존; 전체 backend/sibling은 외부 WSREP 장애로 미복구.
