## 목표

2026-11-04 사용자가 승인한 최근24시간 로그 분석의 모든 항목을 순서대로 조치한다. 과거 로그의 실패는 ground truth로 보존하며 실패를 다시 유발해 확인하지 않는다. 실제 현재 상태·원인·기존 수정을 구분하고, 수정 후 안전한 경로와 기능을 검증한다.

## 범위

1. MCP SQL106/목록·OAuth 복구 수용과 bootstrap, K3s/Waygate restricted native reads, Lumen/Drover/Palimpsest/K3s403, mail payload/소비자 격리, Redis/Sentinel/worker coordination.
2. topology·policy catalog·usage schedule·auth 지연, probe/telemetry 양·controller1 수집503, instance health401/lifecycle, flavor warning·Hub claim405/readiness503, console500/owner502/overview503/OAuth 분류, 테스트/개발/운영 로그 분리.
3. `add-semantic-experience-replay`의 합의한 의미 기반 경험·실행·표시 결과 연결과 안전한 읽기 전용 조회. 원문 입력/DOM/채팅/terminal·credential 수집 금지와 업무 no-replay를 유지한다.

## 보존·제약

공유dev와 다른 세션 index/WIP를 보존한다. 사용자 데이터·기존 키·grant·native IAM·unknown 원장은 삭제/자동 재전송하지 않는다. Source fix/local 검증과 release/운영 수용은 분리한다. 기존 운영 schema 복구를 재적용하거나 미검증 형제 서비스 이미지를 즉흥 교체하지 않는다. 보호된 복구점·정확한 revision·native/schema 호환성이 없는 운영 변경은 차단 근거와 필요 선행 조건을 남기고 모든 접근 가능한 source 작업은 계속한다. 실제 end-user session이 없으면 인증을 우회하거나 저장 자격으로 사용자 impersonation하지 않는다.

## 완료 기준

각 항목의 근거·원인·조치/정상거부/외부 blocker와 실제 검증을 기록한다. 변경한 contract의 behavior 회귀와 실제 smoke·게이트·문서를 완료한다. Source만 수정한 항목을 운영 복구 완료로 표기하지 않는다. 의미 재생은 명세나 가짜 UI/저장으로 완료 처리하지 않는다.
