## Implementation Tasks

- [x] 기존 주소 provenance·origin·국가 집계 원인과 privacy/운영 경계를 확인한다.
- [x] bounded 비국가 대역 집계·snapshot 모델과 회귀를 구현한다.
- [x] frontend parser·responsive 대역 표시·지원 locale·소비자 회귀를 구현한다.
- [x] focused/monitoring 및 실제 Redis/HTTP·브라우저 smoke를 검증한다.
- [x] architecture/API/design/changelog·검증 기록을 갱신하고 archive한다.

## Verification boundary

- Focused backend94/native Redis10/frontend138·monitoring955backend/767frontend 및 actual HTTP/Chromium108responsive+30filter 조건 통과.
- 전체 gate는 backend10255passed/94skip 뒤 RBAC6건의 non-loopback Keystone DNS teardown 오류로 실패. Guard 완화/skip 없음. 후속 독립 frontend5490/457files+runner9,contracts183,functional167/33deselect,Ruff750 통과는 full-gate 성공과 구분한다.
- Private config를 제외한 byte동일 application source의 격리 dev에서는 frontendgeneratedconfig준비 후 `UV_NO_SYNC=1 npm run test:gate`exit0:backend10254/95skip,frontend5490/457files+runner9,contracts183,functional167/33deselect,Ruff750. Snapshot전용rootnode_modules symlink포함digest fc4e8e13ef624067c7a416e058ed21104accd04a62209bd7663ce6cdb70bac32/3528files;working/stagedguard통과. 공유private 문맥6오류의기록은유지한다.
- 실제 backend314range/kind×2basis→실제 frontendparser628행smoke통과.
- Proof: `~/.local/share/afterglow-proofs/nonpublic-traffic-ranges-20261028/verification.json`; 상세 `docs/testing.md`의2026-10-28 비국가 IP 대역 절.
- Source-only. No production/config/SQL/IAM/commit/push; historical raw IP 없음, 대역 역할·actual subnet 추정 없음. 새 frontend 전에 backend reader 전환 필요.
