## Implementation Tasks

- [x] 1. 기존 Identity·하이퍼바이저·모니터링·보안·UI 계약을 확인하고 변경 설계를 확정한다.
- [x] 2. 애플리케이션 증명서 관리자 API·서비스·페이지를 구현한다: 사용자별 목록/검색/상세·현재 사용자 생성·역할/프로젝트 경계·확인 후 삭제·1회 secret·native policy 오류.
- [x] 3. 사용자 자격증명 관리자 API·서비스·페이지를 구현한다: 목록/검색/상세·생성·수정·확인 후 삭제·blob 목록 비공개·명시적 비밀 상세·no-store·문맥 변경 폐기.
- [x] 4. 10초 backend compute/controller node exporter probe·counter/gauge 수집·heartbeat·신뢰된 inventory/설정·Redis 유한 history/lease·오류/stale 경계를 구현하고 main lifecycle에 연결한다.
- [x] 5. 하이퍼바이저 탭에 compute/controller 연결 상태·관측 시간·latency·heartbeat와 CPU/메모리/파일시스템/RX/TX 소형 그래프를 구현하고 네 언어·반응형·인증 문맥 fence를 적용한다.
- [x] 5a. compute/controller/storage 인프라 토폴로지를 실제 LLDP·neighbor·route 보고와 연결하고 허용된 directed host pair의 10초 TCP reachability를 별도 관측한다.
- [x] 5b. NIC별 packets/s·bytes/s와 수신/송신 방향·미측정/stale 상태를 시각화한다.
- [x] 5c. 허용된 목적지의 호스트별 경로 진단·hop·router IP·RTT·미응답 결과를 네트워크 지도에 통합한다.
- [x] 5d. 국가별 요청·응답·성공·실패와 관측 접속 경로를 세계지도에 표시한다.
- [x] 5e. 사이트/API의 고유 방문자 추정·페이지뷰·요청량·전송량·오류·기간별 추이를 실제 수집 집계와 연결한다.
- [x] 5f. 사용자별 로그인 시각·최근 활동·유효 세션·기간별 활동 분포를 기존 auth/Redis 데이터로 제공한다.
- [x] 6. 관련 backend·frontend/config/i18n 검증과 실제 HTTP native SDK·10초 수집·compiled Chromium 작업/장애/반응형 smoke를 실행한다. 합성/provider/운영 한계를 구분한다.
- [x] 7. 실제 smoke 후 API·설정·아키텍처·디자인·changelog·검증 문서를 갱신하고 architecture guard와 OpenSpec archive를 완료한다.

## Verification boundary

Monitoring backend304/frontend263, access326/38, config256/12; 후속 topology81·native Redis4 통과. 실제 SDK HTTP credential CRUD/denial/recovery, Redis+SQLite login/traffic, Linux NIC/TCP/traceroute, compiled Chromium240locale/theme/width조건을 실행했다. Frozen public source의 architecture working/staged digest는 `1d4708475cb3a1c857d6e4c684485d1b285a1099ffa26d0f456a580bf46cc75d`(2735files)다. Private config/shared index/review marker·운영 배포는 변경하지 않았다.

전체 gate는 무관한 동시 WIP storage selector의 `tests/test_backup_dispatcher.py` 부재로 orchestration174passed/1failed에서 중단했다. Svelte check는 범위 밖 database instances PageState 오류1개와 기존 warning3개다. 정확한 로컬/합성·운영 미검증 경계, 초기 fixture 실패와 수정, raw receipts는 `docs/testing.md`의 관리자 자격 증명·호스트·접속 모니터링 절에 기록했다.
