## Implementation Tasks

- [x] Native accounts identity-only 도메인과 personal 이름+random 문자·숫자 생성 및 직접 member provisioning/readback을 구현한다.
- [x] Personal primary·workspace·scope·recovery에서 member 기반 provenance를 검증하고 기존 identity/grant와 조직 owner 보호를 유지한다.
- [x] 관리자 생성은 선택 도메인 Default에 자동 가입시키지 않으며 공개 가입·OIDC·초대의 신규 계정 계약과 endpoint 회귀를 갱신한다.
- [x] 관리자 생성 modal의 misleading 조직 가입 안내·결과를 제거하고 아홉 locale을 갱신한다.
- [x] Exact backend selector 및 auth/access 관련 target과 실제 HTTP/browser 생성 시나리오에서 accounts home·personal 이름·직접 member·Default 비참여와 기존 계정 보존을 검증한다.
- [x] 아키텍처·상세 문서·변경 이력·검증 영수증을 갱신하고 change를 archive한다.

## Verification

- Actual TCP public signup/admin creates and compiled administrator create button produced accounts identities and generated personal projects with exactly direct native member and no observed/identity Default admission. Native SDK loopback re-login and native directory readback agreed; SMTP/IdP/native directory/admin identity are synthetic.
- Auth771backend/440frontend and access1143/181 passed;108locale/theme/width modal conditions had no horizontal overflow. Final frontend4801, contracts159, real-datastore functional166 and Ruff check/714-file formatting passed.
- Final full gate is **not green**: backend8625passed/95skipped/1failed because the layer-build test's temporary HTTP server received an unexpected language-server RetrieveUserQuotaSummary POST. Its origin remains unknown; no ignore, exclusion or account-code workaround was added. Earlier backend8626pass was before the formatting-only correction, not a successful final gate.
- Final working/owned-index staged source digest is aad0734700a3668fdf13a60471532b4f52ad922c0e30a0ba495c30e7650a6079/3394files. Main spec strict validation passed; rapid planning artifacts are complete. Legacy strict change validation requires absent delta-specs and is not claimed as passing.
- Source/runtime boundaries, warnings and receipts are in verification.json and docs/testing.md. No production IAM/config/schema/mailbox/IdP acceptance, commit/push or deployment; existing identity/credentials/grants and user index remain unchanged. Owned browser/HTTP/frontend and three tmpfs datastores were stopped and removed.
