## Implementation Tasks

- [x] 1. 첨부 상태·현재 source·runtime/log 경로를 대조하고 안전한 증거를 수집한다.
- [x] 2. 로딩 중/후의 dashboard 골격·차트/표 위치·크기 변화를 수정한다.
- [x] 3. 데이터 있음/없음/실패 chart/table 상태의 표면·배치를 두 테마에서 일관되게 만든다.
- [x] 4. VM metrics의 host exporter 노출 원인을 수정하고 project/instance-owned metrics를 사용한다.
- [x] 5. Sidebar/drawer의 전역 VM 생성 CTA를 제거하고 instance 페이지 및 tutorial 생성 진입을 유지한다.
- [x] 6. Volume/database backup glyph를 수정한다.
- [x] 7. 모든 서비스 버튼을 명확한 상위 탐색 제어로 정리한다.
- [x] 8. 인증 지연·cache·반복실패503을 조사하고 확인된 원인을 수정한다.
- [x] 9. 실제 브라우저/런타임과 관련 회귀를 검증하고 문서·아키텍처·changelog·receipt를 갱신한다.
- [x] 10. 미검증 범위를 명시하고 completed rapid change를 archive한다.

## Verification disposition

Source-only UI/API fixes and read-only incident diagnosis complete. Actual current DB endpoint is Galera Initialized/Disconnected/wsrep OFF; no cluster repair/restart/bootstrap or deployment was authorized or performed. The independent organization-auth SQL lifetime fix preserves native checks and has failing-before/passing-after evidence; it does not repair the database.

Final frontend5810/475files, contracts183, functional167, focused backend87 and nativeTCP8cases passed. Full gate is NOT green: earlier frozen backend run has4 concurrent CloudShell test failures; final global format-check has3 concurrent CloudShell files. Unrelated changes were neither suppressed nor rewritten. Exact separate source hashes and receipts are in verification.json and docs/testing.md.
