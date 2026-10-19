# Afterglow 보안 모델

이 문서는 Afterglow 백엔드 (FastAPI) + 프론트엔드 (SvelteKit) 의 보안 모델과
주요 가드레일을 정리합니다. 보안 패치 이력은 [CHANGELOG.md](../CHANGELOG.md) 와
[docs/releases/](releases/) 를 참고하세요.

---

## Dependency 보안 floor

1.30.0 후보의 dependency 보안 갱신은 application policy와 별도다. Vulnerable range를 벗어난 최소 compatible package만 갱신하며 lock을 무시한 설치나 unrelated `--upgrade` 전체 갱신을 하지 않는다.

| Consumer | Patched floor / lock | 경계 |
| --- | --- | --- |
| Backend JWT | PyJWT `>=2.15.0` | access/refresh의 단일 `HS256`, 서버 secret과 서명 우선 검증 유지 |
| Backend TLS concurrency | AnyIO `>=4.14.2` | IDNA hostname 검증, TLS verify·configured CA 유지 |
| Backend/OpenStack CLI/Kolla operator HTTP | urllib3 `>=2.8.0` | response decoding/chunk line·HTTPS proxy TLS upstream patch; 운영 `uv sync`나 role promotion과 별도 |
| Backend SSH | AsyncSSH `>=2.24.0` | 기존 SSH credential·host-key policy를 변경하지 않음 |
| Backend PDF package | pypdf `==6.19.0` | PDF thumbnails와 upload 검사 정본은 기존 pypdfium2; installed pypdf의 parser advisory도 vulnerable range 밖으로 유지 |
| Frontend SSR serializer | devalue `>=5.9.3`, 5.x override | SvelteKit payload serialization과 script escaping 유지 |
| Frontend HTML/SVG sanitizer | DOMPurify `>=3.4.16`, 3.x | `renderMarkdown`·Mermaid sanitizer options를 변경하지 않음 |
| Frontend trusted config parser | smol-toml `>=1.7.1`, 1.x | SSR 설정 파일 계약 유지 |
| Frontend development test UI | Vitest·coverage family `>=4.1.11`, 4.x | test UI/network boundary upstream patch; CI selector와 suites 유지 |

Backend `uv.lock`, frontend Bun·npm lock, root CLI `uv.lock`, operator `uv.lock`은 각각 실제 설치 그래프다. Security floor 업데이트로 서비스 tag/Kolla source pin·release version·사용자의 운영 config/volumes를 변경하지 않는다. Default-branch Dependabot 경고 수는 현재 dev의 수정 여부나 운영 exploitability를 대신하지 않는다. [PyJWT PEM](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-ffc3-869f-jxw9), [PyJWT payload](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-42vr-xj54-vc7v), [AnyIO IDNA](https://github.com/agronholm/anyio/security/advisories/GHSA-82r6-8w77-94w6) 같은 library regression은 실제 실행으로 확인하되 production 인증 우회가 재현됐다고 확대하지 않는다.


## 인증·인가 모델

브라우저 access JWT는 Redis refresh family를 가리킵니다. 서버는 저장된 호출자 소유의 unscoped native 로그인 증명을 검증한 뒤 현재 도메인·프로젝트 멤버십과 역할로 요청용 project token을 교환합니다. 로그인 증명과 파생 project token을 분리하므로 프로젝트 role 회수 자체가 로그인 family 삭제를 요구하지 않습니다. SDK Connection의 실제 native scope·논리 대상 구분과 `assert_resource_owner`의 최종 소유권 검사는 그대로 유지합니다.

### 명시적 역할 연결과 프로젝트 권한 경계

- 전역 역할 CRUD·inference edge 편집·프리셋 적용은 현재 검증된 시스템 관리자만 수행합니다. 프로젝트 reader나 native 역할 이름만으로 이 경계를 통과하지 않습니다.
- 시스템 관리자가 선택한 전역 custom 하위 역할은 프리셋 목록 밖 이름이라는 이유만으로 차단하지 않습니다. 실제 Keystone DAG로 상속하며 프리셋 재적용이 이를 삭제하지 않습니다. Custom 이름은 native 서비스 정책의 안전성 증명이 아니므로 연결한 관리자가 해당 정책을 검토합니다.
- 전체 전이 graph에서 알려진 core/project/service 등급 권한을 기존 ceiling으로 검증합니다. Custom alias로 `admin/manager`, reader의 native `member` 또는 관리형 쓰기 권한, 소유권·도메인·순환 제한을 우회할 수 없습니다. 캐시된 token 이름이나 preset의 가상 확장으로 권한을 만들지 않습니다.
- 프로젝트 멤버 API는 같은 그래프의 기존 canonical 등급을 사용할 수 있지만 custom 역할을 독립 위임 대상으로 추가하지 않습니다. Metadata/lease 장애의 fail-closed, 직접·그룹·상속 변경의 현재 권위·projection 무효화와 감사 lifecycle은 유지합니다. 역할 변경만으로 로그인 family를 일괄 회수하거나 철회된 권한을 다음 로그인까지 남기지 않습니다.

### 토큰 lifecycle (Keystone)

- **로그인 증명과 현재 권한**: Redis refresh record에는 unscoped 로그인 증명을 저장합니다. 매 인증 요청은 native 증명과 현재 프로젝트 권한을 확인하며 역할을 담은 검증 결과를 요청 간 TTL cache로 재사용하지 않습니다. Legacy 검증 cache 제거는 이전 worker와의 정리를 위한 것이며 인가의 근거가 아닙니다.
- **프로젝트 접근 상실**: 일반 리소스 작업은403으로 거부하지만 유효한 로그인·도메인 정책 아래 인증 문맥과 projectless refresh를 통한 다른 프로젝트 선택은 허용합니다. 논리 관리자 workspace는 현재 system authority·선택 대상 검사를 유지하며 원래 connection project를 잃으면 실제 native 범위만 projectless가 됩니다. 인증 조회·refresh는 grant를 재생성하지 않습니다.
- **logout / 명시적 revoke**: Redis family 삭제와 캡처한 로그인 증명의 native revoke를 수행합니다. 계정 차단·절대 만료·진짜 native 로그인 증명 무효를 project-only403으로 낮추지 않습니다. Keystone 자체의 사용자 전체 token 회수(일부 group membership 변경 포함)는 Afterglow가 우회하지 않습니다.
- **session 절대 timeout**: Redis refresh record의 최초 `started_at`을 access/refresh/rescope에서 보존·검사하며 만료 record는 삭제한다. Missing timestamp는 기존 marker/서명된 iat로 TTL을 유지한 채 채운다. 원자적 Lua 회전은 현재 존재·blacklist·deadline을 재검사하므로 동시 refresh 중 한 요청만 성공한다.
- **수명 관측 경계**: 정본 격리 HTTP/Redis에서 서명 JWT·회전의 원래 시작 시각과 절대 만료를 검증하고, 공유 세션은 bounded read-only Redis와 기존 사용자 native token의 단일 GET으로만 관찰했다. Refresh/native 만료가 뒤에 있어도 absolute deadline은 유지한다. 합성 세션의 deadline 이동만으로 실제 사용자1시간 자연 경과를 수용했다고 주장하지 않는다. Source/build/runtime·브라우저 relay·VM boot의 별도 제한은 [`docs/testing.md`](testing.md)에 기록한다.
- **원자적 family 회수**: Redis Lua는 refresh/작업 전환과 같은 직렬화 경계에서 현재 family/JTI를 제거하고 그 시점의 native token을 캡처합니다. 이전 JTI alias는 최신 family 회수 대상으로만 해석하며 이전 bearer를 되살리지 않습니다. 이후 각 captured token의 native revoke를 수행하므로 느린 native 호출 전에 Afterglow 자격은 제거됩니다. Strict recovery caller는 모든 captured token을 시도한 뒤 실패를 알리며 삭제한 family를 복원하지 않습니다.
- **정확한 native revoke 증거**: 회수할 subject token이 reset으로 이미 무효여도 operator 인증으로 그 exact token을 revoke합니다. Native token endpoint의 정확한404 `Failed to validate token`/`Could not recognize Fernet token`만 이미 무효화로 수용합니다. 일반 proxy/endpoint/directory404, 권한/연결 오류는 성공 증거가 아닙니다. 이 회수는 Afterglow가 캡처한 세션/token 범위이며 모든 외부 IdP 세션·직접 발급 Keystone 자격·application credential 전체 회수 보장이 아닙니다.

### Canonical 이메일 소유권·provider 연결·가입

- Email은 normalized host 및 case-insensitive 전체 주소로 global native inventory에서 유일성을 검사합니다. 불완전/paginated/truncated inventory를 계정 부재로 해석하지 않습니다. 기존 중복 계정은409로 차단하고 exact user/home·issuer/sub·IdP/protocol tuple·grant/소유권을 검토한 명시적 이관을 요구하며 자동 merge·password reset·identity 이동/복제를 하지 않습니다.
- 외부 identity key는 stable `issuer + sub`(GitHub는 configured API URL + numeric ID)입니다. Verified email 일치만으로 기존 계정을 연결하지 않고 browser-bound600초·1회용 암호화 link ticket과 **기존 계정 password 또는 현재 authenticated native 계정** proof를 요구합니다. Ticket 소비 후 실패는 재로그인해야 하며 다른 username/password/user/home/email proof로 우회하지 못합니다. Proof 검증과 attachment는 같은 graph lease 안에서 수행합니다. Authenticated proof는 native token과 origin refresh record의 exact user/home·blacklist·expiry·원래 absolute deadline도 재검사합니다. 직접 password proof 또는 살아 있는 password-origin authenticated 세션만 local-password marker를 확정하며 federated-origin proof로 추정하지 않습니다. 연결 PATCH는 native user의 전체 federated tuple과 stable metadata를 갱신하며 원래 password/home/name/email/default project 및 다른 연결을 보존·readback합니다.
- 연결 완료와 로그인은 별도 경계입니다. Exact native tuple·stable metadata 저장 확인 뒤 두 link API는 연결 결과만 반환하며 native federation·프로젝트 scope·provider 검증 stamp·새 application session을 발급하지 않습니다. 기존 세션은 유지합니다. 별도 새 authorize/callback에서 canonical native user/home·provider revision·admission을 다시 검사해야 로그인할 수 있으며, 저장 확인 실패503이나 transport timeout을 성공 안내로 바꾸거나 proof를 자동 재사용하지 않습니다.
- Home identity, working domain, provider origin을 분리합니다. Password 로그인은 도메인 selector 없이 global unique username/email 계정의 실제 home에 한 번만 credential exchange하고 최초 세션을 home에 발급합니다. 중복 native 계정을 임의 선택하거나 password를 순회하지 않습니다. Federated 최초 세션도 exact native home에 발급하되 `provider_domain_id`와 provider/revision/login_email을 저장·회전 때 보존하고 provider-origin 정책 및 작업 도메인 email 정책을 각각 확인합니다. Missing origin인 과거 세션은 재로그인하며 현재 작업 도메인으로 추정하지 않습니다. 로그인 후 chooser의 표시 선호·클라이언트 claims는 scope/권한 근거가 아니고 명시적 전환 API가 현재 native 멤버십·원래 수명을 검증합니다.
- 공개 `/auth/login-options`는 활성 도메인의 현재 허용된 공급자 등록 metadata만 반환합니다. 등록 origin ID는 authorize handle일 뿐 계정의 home/조직 멤버십을 만들지 않습니다. Secret/client ID/endpoint·이메일/사용자 directory와 issuer discovery는 이 목록에 포함하지 않습니다. 신규 human의 필수 개인 도메인·승인/동결 quota·enrollment 완료 guard는 유지하며 기존 Default 계정·home은 자동 이동하지 않습니다.
- Provider 노출 `allow_providers`는 admission이 아닙니다. 기존 멤버십이 없으면 provider별 configured `auto_join_email_domains`의 exact host가 필요하며 기본은 거부입니다. Domain map 생략은 default 상속, 명시 map은 전체 대체, `{}`·누락 provider·빈 host 배열은 자동 가입 없음입니다. Auto-join은 prepared Default reader만 추가하고 기존 계정 연결 proof/manager·owner 권한을 만들지 않습니다.
- Public signup은 별도 `[auth].public_signup_enabled` opt-in과 `signup_email_domains`(빈 list는 host 제한 없음)입니다. Email-first 링크 전달 후 새 개인 home만 만들며 임의 도메인의 공개 등록 route는403 `invitation_required`입니다. 계정 존재/home 안내는 전달된 비밀 링크 조회 뒤에만 노출합니다. 기존 계정은 로그인/복구·초대 수락으로 재사용합니다. 기존 SQL signup 정책 projection은 이 공개 가입이나 domain admission 권한이 아닙니다.
- Native mapping은 stable subject의 user-only ephemeral `user.id` mapping이어야 합니다. Mutable preferred_username/email mapping, email 덮어쓰기, groups/projects/roles provisioning은 허용하지 않으며 native exchange 전에 unsafe/unavailable mapping을503 `native_mapping_unsafe`로 거부합니다. Native full `federated` tuple PATCH 및 canonical user ID/home 발급은 별도 운영 prerequisite이고 service token impersonation fallback은 없습니다.

### 이메일 소유 기반 복구·프로필 이메일 변경

- Public username/password 요청은 유효한 email이면 계정 부재/중복/부적격·SMTP 비활성/실패·directory/DB/Redis 장애·주소 budget 거부에도 동일202 `{accepted:true}`입니다. Schema/invalid email422 및 IP route-limit429는 별도이며202는 실물 메일 전달 증거가 아닙니다. 주소 budget은 hashed Redis key60초로 종류/IP 사이에 공유합니다.
- Global unique email을 가진 enabled local-password 사용자와 enabled home만 대상입니다. 사람의 system admin/manager는 이메일 소유로 복구할 수 있습니다. Configured operational `os_username`, effective `service` 역할과 external-only 사용자는 제외합니다. Federated 계정도 명시적으로 local password capability가 검증/설정되었다면 가능하며 external-only 사용자에게 복구로 password를 만들지 않습니다.
- Migration097 `account_recoveries`는 SHA-256 token hash·exact user/home/original email·kind/status/expiry만 보존하며 password/평문 token은 저장하지 않습니다. 발급부터1시간·1회용, 전달 완료 `pending`만 redeem합니다. Username GET은 소비하며 password/email-change inspection은 소비하지 않습니다. 매번 현재 identity/email·유일 소유권·eligibility를 다시 검사합니다.
- 본인 email 변경은 access bearer와 exact home current-password 재인증, global unique 새 주소와 현재 email 정책, 기존 주소의 token/신규 주소 없는 알림 및 신규 주소 proof 전달을 요구합니다. 일반 profile PATCH는 email 변경에409 `email_verification_required`이며 직접 소유권을 바꾸지 않습니다. Manager/system-admin의 별도 관리 경로 권한을 본인 profile 우회로 쓰지 않습니다.
- Password/email native dispatch 전 SQL에 `dispatching`을 commit하고 다른 pending mutation proof를 supersede합니다. Native 거부·timeout·취소·crash도 replay 불가입니다. 성공/불명확 outcome 모두 captured Afterglow/native sessions 회수를 시도하며 unknown502 `recovery_outcome_unknown`/회수 실패503 `recovery_sessions_failed`를 성공으로 숨기지 않습니다. `dispatching/outcome_unknown/sessions_failed` journal을 보존해 운영자가 exact native 효과와 회수를 조사합니다. Automatic native rollback/reset/replay는 없습니다.
- 복구 모든 응답(429 포함)은 no-store/private·no-cache·no-referrer입니다. 링크 token·password·provider bearer를 audit/log/분석에 기록하지 않습니다. API payload/error와 rate-limit의 정본은 [인증 API](api/auth.md#이메일-소유-기반-계정-복구프로필-이메일-변경),096/097 schema-before-writer·구형 writer drain은 [배포 가이드](deployment.md#canonical-계정공개-가입복구-cutover)를 따릅니다. 이 계약은 운영 rollout·real mailbox 수신·최종 실제 GitLab/native acceptance 증거가 아닙니다.

### 브라우저 access/refresh 복구

- `frontend/src/lib/api/client.ts`의 `fetchWithAuth`는 명시적 access token을 붙이는 first-party 요청의 HTTP handshake를 담당한다. JSON API와 채팅/SSE·첨부·다운로드 소비자가 같은 경로를 사용하고, 진행률 XHR 업로드도 같은 인증 복구 정책을 사용한다.
- 현재 세션의 access 만료가 120초 이내이면 요청 전 refresh를 기다린다. 진행 중 갱신에 들어온 요청도 같은 Promise를 기다리므로 background-tab timer가 늦어져도 만료 토큰으로 요청부터 보내지 않는다.
- 첫 401은 refresh 또는 이미 회전한 live token으로 **한 번만** 재시도한다. body·project·사용자 취소 신호를 보존하며, 이미 HTTP 응답을 받아 소비 중인 SSE를 재시작하지 않는다. 취소된 요청은 갱신 뒤 재전송하지 않고 공유 refresh는 다른 요청을 위해 완료한다.
- 진행 중 프로젝트/도메인 commit은 일반 foreground/periodic refresh와 늦은401 처리의 소유권 경계다. 첫 응답과 재시도 응답 모두 commit 반영을 기다린 뒤 실제 거부된 bearer·logical login/user/home/working/project가 여전히 현재 것인지 확인한다. 같은 scope라도 새 bearer를 과거401로 지우지 않으며, 비동기 인증 정리에는 verification epoch를 적용한다. Non-replay 변경은 자동 재전송하지 않고 세 번째 전송도 하지 않는다. 원래 `started_at`·만료·회수 정책은 그대로 유지한다.
- root layout은 mount, window focus, document visible 복귀 시 즉시 만료를 확인하고 60초 interval도 유지한다. mockup과 logout 중에는 lifecycle 갱신을 시작하지 않는다.
- refresh 자체의 401, 폐기/차단된 Redis 세션, 서버 session timeout, Keystone 인증 만료는 재로그인 대상이다. Keystone token authentication의 `Failed to validate token` 및 `Could not recognize Fernet token` 404는 adapter에서 Unauthorized로 정규화하며, 일반 endpoint/resource 404는 일시적 검증 실패와 구분하지 못하므로 503을 유지한다. Background refresh의 terminal 결과도 보호 요청을 기다리지 않고 로컬 인증을 지우고 로그인 화면으로 전환한다.
- refresh 503·429·네트워크 오류는 인증 실패로 바꾸지 않고 세션을 보존하되, root shell의 닫을 수 없는 인증 복구 dialog로 작업을 중단한다. 기존 화면은 mounted 상태로 남겨 작성 내용을 유지하고, `dialogFocus`가 다른 화면·overlay를 inert 처리한다. 재시도는 기존 coalescing/cooldown 및 `Retry-After`를 따르며 성공하면 동일 화면을 복구한다. 실패 상태는 해당 access token에 묶이고 다른 로그인·회전·로그아웃 이후의 늦은 응답은 새 identity를 덮어쓰지 않는다.
- Kolla HA에서는 backend가 모든 Valkey Sentinel을 통해 현재 master를 해석하고 `redis_url`의 사용자명·비밀번호·DB index를 발견된 master 연결에 적용한다. replica로 승격 정보가 어긋나거나 master 쓰기가 불가능하면 refresh/session 검증은 503으로 fail-closed하며, 브라우저에서 이를 terminal 401로 바꾸지 않는다.
- 외부/presigned URL은 이 복구 경로와 브라우저 Authorization 주입 대상이 아니다. `downloadAuthenticated`는 설정된 API origin의 `/api/v1/` 경로만 인증하고 다른 URL은 자격 없이 요청한다. logout revocation fence와 늦은 401 보호를 유지한다. 탭 사이 자격 공유나 cross-tab 회전 winner 가져오기는 하지 않는다.
- 명시적 로그아웃은 진행 중인 refresh의 성공/실패를 관찰한 뒤 가능한 최신 token의 서버 폐기를 시도한다. Refresh나 폐기 통신 실패가 있어도 이 기기의 auth/storage는 정리하며, 서버 폐기를 확인하지 못한 경우 이를 경고한다. 일시 장애 때 자동으로 전체 세션을 삭제하거나 인증을 우회하지 않는다.

### 인증·MCP 경계 패치의 동작 및 운영 제한

- GitLab federated login도 실제 요청 IP/fingerprint/device를 password login과 동일하게 저장한다. 기존 origin 없는 legacy 세션은 strict/subnet에서 거부하여 재로그인하며, 현재 호출자의 출처를 원래 login origin으로 채워 우회하지 않는다. off/log 정책은 원래 설정의 비차단 의미를 유지한다.
- 브라우저 자격은 탭의 sessionStorage에만 저장하고 legacy localStorage 자격을 삭제한다. 기존 로그인은 한 번 다시 필요하며 새 탭은 독립 인증한다. 토큰 없는 logout marker만 공유한다. SvelteKit 자동 nonce/hash CSP를 사용하여 script unsafe-inline은 없고 SPA fallback의 실제 HTML과 CSP도 일치시킨다. 이는 JavaScript-readable 자격이나 모든 XSS 위험을 제거한 것은 아니다.
- MCP cancellation/deadline fence는 느린 최종 owner/state GET 뒤 새 provider mutation을 막는다. 이미 HTTP 요청을 전송한 worker는 실제 종료까지 drain하며 connection과 실행 slot을 보유한다. Timeout은 rollback이 아니고 응답이 provider 종료까지 늦어질 수 있다.
- Concurrency set의 UUID member는 본인 요청만 제거하고 TTL 자동 회수는 없다. Crash/release 실패는 capacity를 fail-closed로 유지한다. 복구 전 해당 grant를 쓰는 모든 worker의 종료/drain을 확인하고 승인된 운영 절차로 잔여 member를 제거한다. 살아 있는 worker가 있는 set의 DEL/TTL은 금지한다. Legacy numeric limiter도 drain/만료 후 새 set으로 전환한다.
- 만료 mutation lease는 poll과 cleanup에서 unknown으로 바꾸고 key/record를 유지한다. 동일 grant/source/tool/arguments의 unresolved 작업은 새 key로도 다시 claim하지 않는다. 실제 provider 상태 확인 전 자동 재전송이 없으며 다른 grant로 바꾼 retry까지 전역 deduplication하는 것은 아니다.
- MCP 삭제/lifecycle action은 destructiveHint=true이다. Metadata는 클라이언트 힌트이고 서버 인가·owner 검사·ledger를 대체하지 않는다. 일회성 PAT 발급 응답은 Cache-Control: no-store와 Pragma: no-cache이다.
- MCP VM/빈 볼륨 생성·VM network 연결은 `mcp:write`와 승인된 target-project 자격만 사용하며 Lumen 기본 read-only grant를 확대하지 않는다. `readOnlyHint=false`/`destructiveHint=false`는 생성 비용이나 리소스 변경이 없다는 뜻이 아니다. Preview는 조회만 하고 최종 dispatch는 grant·리소스·SDK deadline을 다시 검증한다.
- Nova keypair owner는 provider 응답의 `user_id`로 증명한다. 설치된 SDK의 `get_keypair(user_id=...)`는 GET query가 아니라 resource body에 입력값을 보충하므로 owner 증명에 사용하지 않는다. 누락·타인 owner는 거부하며 private/public key나 `adminPass`를 결과에 포함하지 않는다.
- VM boot volume은 기본 보존하며 삭제 연동은 명시적 opt-in이다. 입력은 image/flavor/network/크기 등 허용 목록만 사용하고 user data·비밀번호·provider kwargs를 받지 않는다. Network attach는 기존 port를 재사용하지 않고 owned ACTIVE/SHUTOFF parent와 owned/shared network, 새 port의 exact project/network/device binding을 확인한다. 접수 결과는 VM/volume ready나 guest data plane 증거가 아니며 unknown 자동 resend 금지 원장은 세 도구에도 동일하게 적용한다.

### MCP OAuth와 개인 API 키

- Inbound MCP resource는 `https://cloud.dmslab.re.kr/mcp`이며 client는 discovery가 광고하는 `/mcp/oauth/authorize`, `/mcp/oauth/token`, `/mcp/oauth/register`를 사용한다. Authorization URL만 주소창에 입력하는 것은 authorization request가 아니다. 등록한 `client_id`, 정확한 callback/resource, `response_type=code`, 허용 scope, PKCE S256과 state를 포함해야 한다.
- 현재 DCR은 public client(`token_endpoint_auth_method=none`)와 authorization-code·refresh grant 모두를 요구한다. Loopback HTTP callback은 `127.0.0.1` 또는 `[::1]`처럼 IP literal이어야 하며 `localhost`나 arbitrary HTTP callback을 허용하지 않는다. 모든 MCP 제품의 등록 형식과 호환된다는 의미가 아니다.
- Frontend 동의 ticket은 URL에서 제거해 `sessionStorage`에만 보존한다. Password/GitLab login 뒤 미선택 project를 먼저 선택하고, consent GET/approve/deny는 현재 browser access bearer와 `X-Project-Id`가 있는 scoped session에서만 수행한다. Ticket은 권한이나 access token이 아니다.
- 승인은 현재 user/project의 restricted Keystone application credential과 grant를 생성한다. Client에는 opaque access/refresh token만 반환하고 upstream credential은 보내지 않는다. 개인 API 키 발급·검증·폐기는 별도 방식으로 유지하며 OAuth JSON에는 Authorization header나 client secret을 포함하지 않는다.
- 위임 snapshot은 실제 대상 SDK token의 role ID/name과 현재 사용자·프로젝트의 effective 할당/검증된 role DAG의 교집합입니다. 기존 trusted identity reader는 정확한 user/project 역할 metadata만 공급하며 credential 발급·재인증에는 사용하지 않습니다. Current metadata 장애·foreign scope·빈 교집합은 fail-closed합니다. Stale token role 때문에 축소가 필요하면 모든 descendant도 교집합 안에 있는 역할 ID만 명시하고, 그대로인 token은 기존 omitted-role 생성 경로를 유지합니다. 반환 role/project mismatch는 remote ID를 먼저 저장한 기존 cleanup 경로에서 폐기합니다.
- 개인 키만 `non_expiring: true`로 실제 무기한 lifetime을 요청할 수 있다. `expires_at`과 동시에 지정하면422이며 일반 키는 명시한 미래 만료를 사용한다. Migration085의 nullable `DATETIME(6)`와 CHECK는 `source='personal_token'`에만NULL을 허용한다. OAuth/내부 위임은 계속 유한 만료다. Keystone 무기한 credential은 `expires_at`을 생략하고 `unrestricted=False`, 실제 역할·owner/project·폐기·cleanup 경계를 유지한다. 유한 시각은 SQL·공개 응답·SDK에서 UTC microsecond를 보존하며 브라우저에 timezone 없는 만료를 반환하지 않는다.
- Refresh의 필수 `client_id`는 최초 발급 code의 client와 일치해야 한다. 빈 값·다른 client·불명확한 persisted binding은 `invalid_grant`이며 token rotation이나 replay revocation을 일으키지 않는다. `client_id` 생략도 거부하고 올바른 client의 재사용은 기존 family/grant 폐기를 유지한다. Binding은 consumed code row에 남으므로 code expiry·authorization ticket cleanup 뒤에도 유지한다.
- Access token은 15분, refresh token은 최대 30일이며 둘 다 grant deadline을 넘지 않는다. 계정에서 OAuth 접근을 회수하거나 `/mcp/oauth/revoke`를 호출하면 grant/family와 downstream authority를 기존 내구성 cleanup 경로로 폐기한다. Token·code·ticket·upstream secret은 문서·audit·QA receipt에 기록하지 않는다.
- MCP 클라이언트 관측은 인증된 SDK initialize 성공 뒤 현재 grant/epoch/token fence 아래 commit한다. 저장 장애503이나 경쟁 폐기401을 응답하기 전에 성공 헤더를 보내지 않는다. Migration087의 nullable JSON은 최근10개 정제 서명만 보존하며 legacyNULL에서 identity를 만들어내지 않는다. Raw UA·IP·Authorization·token·capabilities는 수집하지 않는다. 이름100자·버전32자의 정제된 표시 값과 고정 추정 label만 owner/anchor-project API의 no-store 응답에 포함한다.
- `clientInfo`와 User-Agent는 모두 위조 가능하다. 같은 신고가 같은 실제 단말이라는 보장, 온라인 상태, 실제 제품 인증이나 권한 근거가 아니다. 비인가된 관측을 제거하려면 기존 grant/API 키 전체를 철회한다. 같은 자격을 공유한 다른 클라이언트도 차단하며 tombstone·감사·upstream cleanup과 OAuth refresh 거부를 유지한다. 이름/UA 차단·관측 행 삭제만으로 credential을 계속 유효하게 두지 않는다.
- SDK 내부 schema cache refresh는 현재 principal에게 허용된 tool schema만 읽으며 cloud 권한을 부여하지 않는다. Client `tools/list`의 page-size·grant-bound cursor와 SDK input/output validation을 유지하고 모든 `tools/call`에서 registry의 현재 principal 권한·strict arguments·mutation ledger를 다시 적용한다. Manage principal의 schema가 cache에 있어도 read grant는 valid mutation을 dispatch할 수 없다. 운영 proof는 HTTP200과 함께 `isError=false` 및 실제 typed tool 결과를 확인한다.

### Lumen MCP opt-in과 ordinary API 키

- Afterglow cloud catalogue GET와 chat admission은 자격을 발급하지 않는다. Same-site browser POST와 현재 `lumen-tools_user`가 명시적 current-project read/manage 승인을 만들며, 실제 provider 역할이 manage를 허용해야 한다. 내부 `consented_at` 없는 legacy grant는 선택과 실행에서 거부한다. 개인 토큰 선택을 조회가 바꾸지 않는다.
- Catalogue의 `project_id`/`project_name`은 선택된 grant의 기본 실행 target을 따른다. 개인 키가 현재 채팅 프로젝트를 제외한 승인 프로젝트만 가진 경우에도 실행 target을 현재 프로젝트로 덮어쓰지 않는다.
- Lumen preview는 read budget, execute는 registry effect별 read/mutation budget과 동일한 Redis grant concurrency slot을 사용한다. 한도 초과429·coordination 장애503은 provider/원장 진입 전에 거부하며 slot은 target 재검증·SDK worker/connection drain 뒤 본인 member만 제거한다. Public MCP transport를 통한 호출은 기존 transport guard만 사용하여 중복 획득하지 않는다.
- Owner generation은 외부 역할 준비 전에 캡처하고 pending reservation·credential activation lock에서 재검사한다. 이후 DELETE·선택 해제가 경쟁을 이기며 뒤늦은 발급은 dispatch되지 않는다. 취소나 credential 생성 결과가 모호하면 기존 tombstone/orphan cleanup 경로로 fail-closed한다.
- Global remote MCP publication은 실행 권한이 아니다. 사용자/project/config-version opt-in과 현재 OAuth token이 함께 있어야 실행되며 activation generation을 frozen selection fingerprint에 묶어 비활성화/재활성화가 이전 대기 승인을 되살리지 않는다. 헤더·OAuth token·application credential은 browser catalogue에 반환하지 않는다.
- Browser consent·deactivation·OAuth-start의 POST/PATCH/DELETE는 시작한 인증 scope의 AbortSignal과30초 deadline을 사용한다. Identity/ready/project/ABA 변경과 component unmount가 controller를 취소하고 generation/scope를 폐기하여 늦은401 복구가 새 계정의 승인으로 재전송되거나 종료한 설정에서 OAuth 이동을 시작하지 않는다. 이는 이미 수락된 upstream 효과의 rollback을 보장한다는 뜻이 아니다.
- Ordinary Lumen 키는 현재 대상 프로젝트의 keys-editor 및 요청 scope ceiling, 사용자 quota 아래에서 이름·scope·월 한도·nullable expiry를 원자 발급한다. Naive/past expiry는 거부하고 현재 키의 active/revoke/expiry와 현재 owner 권한을 다음 요청·새 provider/tool I/O 전에 재검증한다. 완료 checkpoint 회수·정산을 소급 취소하지 않는다. Secret은 한 번만 보이며 권한 확인 중에는 숨기고 확정 거부·actor/project/ABA 전환에서는 폐기한다.
- Migration086과 native migration026은 backfill로 legacy consent를 만들지 않는다. Schema-before-writer와 API/worker 동시 cutover가 필요하다. 실제 production snapshot·원래 암호화 키·ledger·기존 writer/신규 schema 및 신규 writer/기존 schema의 양방향 호환성·rolling upgrade는 이번 local qualification에 포함하지 않는다.

### Claude Gateway 승인 shell과 BFF 경계

- `/oauth/claude/authorize`는 device verification URL로 직접 열 수 있는 public UI shell이다. Complete-link의 `user_code`는 허용 alphabet/length로 검증·정규화해 `sessionStorage`에만 보존하고 `history.replaceState`로 query를 제거한다. Page response와 document는 `Cache-Control: no-store`, `Referrer-Policy: no-referrer`를 사용한다.
- Shell 진입 marker는 password/GitLab login과 project selection을 거쳐 같은 route로 복귀시키지만 권한 자체가 아니다. Approve/deny는 access bearer와 current `X-Project-Id`가 필요한 `/api/v1/chat/claude-gateway/authorize` BFF에서만 가능하다. Catch-all Lumen proxy의 `Depends(get_token_info)`가 unauthenticated request를 401로 거부한다.
- Afterglow는 device code, issued Gateway API key 또는 provider credential을 DB/localStorage에 저장하지 않는다. Lumen이 user/project binding, hashed grant/key, one-time consume, fixed scope와 24시간 expiry를 소유한다. UI는 current project, exact scopes와 expiry를 승인 전에 표시한다.
- Invalid/expired/consumed code는 safe OAuth reason을 사용자 행동으로 바꾸어 새 Claude Code connection을 안내한다. Browser/client logs와 analytics에 query code나 credential을 넣지 않는다.

### 전역 Cloud Shell 자격·격리 경계

- Cloud Shell 승인은 현재 Afterglow access JWT와 `X-Project-Id`를 다시 검증하고, Keystone에서 같은 사용자·프로젝트로 scoped된 token의 사용자/project/만료를 대조합니다. 만료까지 120초 미만인 token은 새 세션에 사용하지 않습니다.
- Redis ticket에는 scoped Keystone token이 짧은 `ticket_ttl_seconds` 동안 포함됩니다. 티켓은 high-entropy opaque 값이고 목적(`cloud-shell`)이 묶이며 원자적으로 한 번만 소비됩니다. Consume 뒤 ticket key는 삭제되고 active ownership key에는 token 대신 서명된 fingerprint/session metadata만 남습니다. Redis가 불가하면 ticket/lock/heartbeat 경로는 503/4500으로 fail-closed합니다.
- 브라우저는 Keystone token, 서비스 프로젝트 자격, Zun exec URL을 받지 않습니다. Backend가 Zun binary WebSocket에 직접 연결하고 browser에는 configured public Afterglow API relay만 노출합니다. Frontend CSP `connect-src`는 설정된 API HTTP(S) origin과 정확히 대응하는 WS(S) origin만 추가합니다. Handshake 뒤 `Origin`을 frontend/CORS allowlist와 정확히 비교하며 누락·userinfo·path/query가 있는 origin도 거부합니다.
- Bootstrap은 PTY echo를 먼저 끈 뒤 bounded payload를 받고, token을 `/dev/shm/afterglow/secure.yaml`의 UID/GID 1000·mode 0600 파일에만 씁니다. `/dev/shm`은 컨테이너 tmpfs이고 영구 Cinder mount `/home/cloudshell`과 분리됩니다. 그 뒤 UID/GID 1000, 빈 supplementary group, `no-new-privs`, 비어 있는 inheritable/ambient/bounding capability로 `bash --login`을 exec합니다. Image layer와 persistent home에는 credential을 쓰지 않습니다.
- Image/CLI/bootstrap source와 all-four runtime build gate는 독립 `openstack-afterglow/openstack-client` 저장소가 소유합니다. SDK에는 top-level `clouds` mapping의 public config와 별도 secure config를 명시적으로 선택하게 하며 shell 환경에는 token 값 대신 `OS_CLIENT_CONFIG_FILE`/`OS_CLIENT_SECURE_FILE` 경로만 둡니다. 비공개 image credential은 native Zun registry가 관리하고 Afterglow에는 UUID만 설정합니다. 미게시·pull·policy 오류를 다른 image/권한으로 우회하지 않으며 영구 홈은 유지합니다. Source 저장소와 초기 GHCR package는 private으로 유지하고 실제 package ACL·compute pull 권한을 별도로 검증합니다.
- Zun 컨테이너는 비특권(요청에 `privileged`를 보내지 않아 Zun 기본값을 쓰며, Zun 기본 policy는 명시적 privileged 생성을 모두 거부), 고정 CPU/RAM, 전용 프로젝트의 default 네트워크(또는 명시적 소유 네트워크), 한 개의 managed home volume을 사용합니다. 네트워크의 subnet과 external 연결을 홈 생성 전에 확인하며 다른 프로젝트의 private network는 거부합니다. 기본 `default` security group은 전용 프로젝트 안에서 exact ID로 확정하고 기존 규칙을 유지합니다. Egress-only를 보장하지 않으므로 같은 그룹의 세션 사이 ingress도 운영 정책으로 관리해야 합니다. 세션 정리는 owner 권한의 `stop=true` 삭제를 사용하므로 service user에 force delete용 admin 권한이 필요하지 않습니다. Dedicated project service credential은 lifecycle에만 사용하고 shell 안에는 caller-scoped token만 들어갑니다.
- 영구 홈과 컨테이너는 이름만으로 채택/삭제하지 않습니다. HMAC signature, service-project resource metadata, user/workspace/session fingerprint, expiry가 모두 맞아야 합니다. 중복·collision·metadata 불일치·조회 실패는 자동 정리 대신 fail-closed 상태로 남깁니다.
- 사용자당 전역 singleton reservation/active key가 다른 탭과 프로젝트의 동시 세션을 막습니다. Project switch/logout은 먼저 relay를 닫고 container cleanup을 요청합니다. Idle/max expiry, browser disconnect, backend restart 뒤에는 exact managed container cleanup과 startup/interval reconciler가 보조하지만 persistent home은 명시적 reset 전까지 유지합니다.
- Audit은 `cloud_shell.start`, `cloud_shell.end`, `cloud_shell.reset`의 project/user/status와 safe error code만 기록합니다. Ticket, Keystone token, bootstrap payload, exec URL, terminal bytes는 audit/application log에 기록하지 않습니다. Terminal 내용 자체는 Afterglow DB에 저장하지 않습니다.

주요 위협과 남은 경계:

| 위협 | 완화 | 남은 운영 책임 |
|---|---|---|
| Ticket 재사용·다른 protocol 사용 | purpose-bound atomic consume, 짧은 TTL, user-wide reservation | Redis TLS/auth와 접근 제어 |
| Cross-site WebSocket hijacking | exact Origin allowlist, opaque ticket | 공개 ingress의 HTTPS/WSS 및 WebSocket upgrade |
| Token의 영구 홈 유출 | PTY echo off, tmpfs 0600 config, ephemeral container, token은 home에 미기록 | Zun compute/root와 memory dump 접근 통제 |
| 서비스 프로젝트 resource 탈취/오삭제 | dedicated project, signed exact metadata, duplicate/collision fail-closed | project/network/security-group/quotas와 `SECRET_KEY` lifecycle |
| 컨테이너 escape·네트워크 남용 | non-privileged, no capabilities, no-new-privs, fixed resources, project-owned SG | Zun runtime hardening, registry provenance, SG ingress/egress 정책과 같은 그룹 세션 간 접근 통제 |
| 중단 뒤 orphan | lease heartbeat, exact cleanup, startup/interval reconciliation | cleanup alerting, staging expiry 검증, 수동 보존 정책 |

### 리버스 프록시 IP 추출

- `X-Forwarded-For` / `X-Real-IP` 헤더는 `settings.trusted_proxies` (CIDR 리스트)
  안에서 들어온 요청에만 신뢰
- 외부 직접 요청의 헤더는 무시 (위조 가능)
- 기본값: `127.0.0.1/32, ::1/128`

---

## Defense-in-depth IDOR 가드 (1.14.0+)

OpenStack RBAC (project-scoped Keystone token) 이 1차 방어선이지만, 다음 시나리오에
대비해 백엔드 layer 에서 한번 더 owner 검증을 수행합니다:

- Neutron / Octavia / Cinder / Trove / Manila policy.json 이 광범위하게 열려 있을 때
- admin 토큰이 누설된 후 admin 권한 없이 cross-project 접근을 시도하는 자동화 도구
- 향후 owner-blind 한 SDK 호출이 실수로 추가될 때 회귀 방지

### 핵심 헬퍼

```python
# backend/app/api/common/owner_check.py
from app.api.common.owner_check import assert_resource_owner

# 1. SDK 로 자원 조회 (없으면 404)
res = await asyncio.to_thread(conn.network.get_router, router_id)

# 2. owner 검증 (admin 통과, 불일치 시 404 — enumeration 방지)
assert_resource_owner(res, conn, token_info, not_found_detail="라우터를 찾을 수 없습니다")
```

- `_resource_project_id` 가 `project_id` / `tenant_id` 양쪽 fallback
- `is_system_admin` 토큰은 우회
- 외부 네트워크 (`is_router_external`) / 공유 네트워크 (`is_shared`) / 공개 share
  (`is_public`) 는 cross-project 노출이 정상이라 면제

### 적용 범위 (1.14.0)

| 모듈 | 엔드포인트 |
|---|---|
| `network/networks.py` | get/delete/update network, FIP associate/disassociate/delete, subnet update/delete |
| `network/routers.py` | get/delete + interface/gateway 모두 |
| `network/security_groups.py` | delete + rule create/delete |
| `network/loadbalancers.py` | LB/listener/pool/member/HM 의 모든 sub-path (lb_id 검증) |
| `database/instances.py` | instance + databases/users/backups + restore + **enable_root_user** |
| `storage/volumes.py` | get/delete + transfer |
| `storage/volume_snapshots.py` | snapshot get/delete + create (volume owner) |
| `storage/volume_backups.py` | backup get/delete/restore + create (volume owner) |
| `storage/file_storage.py` | share delete + access-rule list/grant/revoke |
| `compute/instances.py` *(1차 PR)* | get/delete + start/stop/reboot/shelve/unshelve |

### 적용 안 됨 / minimal

| 모듈 | 이유 |
|---|---|
| Object-storage 검증 | Swift 의 account 모델 (project-scoped token = 그 account 의 컨테이너만 접근) 이 1차 방어선으로 충분. 신규 컨테이너에 `X-Container-Meta-Owner-Project-Id` 자동 부착만 (운영 도구 토대) |

---

## K3s 비밀 데이터 암호화 (HKDF v3)

```
master key (k3s_kubeconfig_encryption_key, 64 hex)
    │
    ▼ HKDF-SHA256 (salt=None, info=b"afterglow-k3s/<domain>")
    │
    ├─ sub-key kubeconfig    ─▶ AES-256-GCM (AAD=domain) → "v3:" + base64(nonce+ct)
    ├─ sub-key node_token    ─▶ ...
    ├─ sub-key notion_config ─▶ ...
    └─ sub-key manager_password ─▶ ...
```

- **Key separation**: 동일 마스터키여도 도메인 간 ciphertext 가 cross-decrypt 되지 않음
- **복호화 fallback 순서**: v3 → v2 (마스터키 직접 + AAD) → legacy (no prefix, AAD 없음)
- v2/legacy ciphertext 복호화 시 **deprecation warning 1회** (도메인 단위) 로그
- 다음 릴리스에서 v2/legacy 제거 예정 — 마이그레이션 스크립트로 batch re-encrypt 필요

---

## Audit Log

- 모든 mutation 엔드포인트는 `app.api.common.activity_recorder.rec()` 로
  `(project_id, user_id, resource_type, action, status, resource_id, source_ip)` 기록
- **Kubeconfig 다운로드** 도 매 GET 마다 `action="kubeconfig_download"` + `extra={"source_ip": ...}` 기록 (1.14.0+) — HEAD 는 사전 요청이라 미기록
- **K3s callback** 는 source IP 와 cluster_id 를 logger 에 기록 (audit table 별도 row 는 callback 응답 후 발생)

---

## 입력 검증

| 항목 | 위치 | 검증 |
|---|---|---|
| Object-storage object name | `_sanitize_object_name` | 제어문자/`..`/leading slash/max 1024자 차단 |
| Upload MIME / 크기 | `object_storage/upload.py` | `app_max_upload_gb` (기본 10GB) |
| K3s `allowed_cidrs` | `models/k3s.py` | `IPvAnyNetwork` Pydantic v2 검증 |
| K3s `node_token` 패턴 | `_NODE_TOKEN_RE` | `^[A-Za-z0-9:_+/=.\-]{8,512}$` |
| K3s callback fields | `K3sCallbackRequest` | `min_length=8` |

---

## Cloud-init 템플릿 (Jinja2)

- `Environment(autoescape=False)` 명시 (YAML/shell 출력에 HTML autoescape 무의미)
- 모든 사용자 입력 변수는 `{{ var | shlex_quote }}` 적용 — shell injection 차단
- `health_check.sh.j2`, `k3s_agent.yaml.j2`, `envmgr_rotate_key.sh.j2`
  - `K3S_TOKEN`, `REPORT_URL`, `INSTANCE_ID`, `SHARE_NAME`, `NEW_KEY` 모두 quoted
  - `envmgr_rotate_key.sh.j2` 는 `printf` heredoc + `NEW_KEY` 형식 정규식 검증

---

## Health Bearer 토큰 (instance_health)

- VM 의 cloud-init 가 backend 로 health 보고 + cephx rotate 권한을 가지는 토큰
- **Lifetime**: 7일 절대 만료 (1.14.0 — 이전: 30일 sliding 으로 사실상 영구)
- VM userdata 노출 시에도 7일 후 자동 만료 → cephx rotate 권한 무효화
- 7일 이상 살아있는 인스턴스는 `health_check.sh` 의 재발급 흐름이 새 토큰 받음

---

## Rate Limiting

- `slowapi.Limiter` 기반, key_func = `_get_real_ip` (`trusted_proxies` 검증 후 추출)
- mutation 엔드포인트별 정책:
  - 인스턴스 create/delete: 5/min, action: 30/min
  - 네트워크/SG/FIP/LB: 10/min
  - K3s create: 2/min, scale: 10/min
  - Volume create: 10/min
- callback 등 인증 없는 endpoint 도 `10/minute` 적용

---

## CORS / RGW

- **백엔드 CORS**: `cors_origin_list` allowlist (wildcard 금지)
- **RGW 버킷 CORS**: `s3.py:_put_bucket_cors` 가 `cors_origin_list` 와 동기화. allowlist 가 비어있으면 CORS rule 자체 삭제 (cross-origin 차단)
- **프런트엔드 CSP 미디어**: `media-src 'self' blob:`만 허용합니다. Audio Studio는 `fetchWithAuth`로 받은 생성 음성 응답이나 사용자가 고른 로컬 파일로 만든 object URL만 재생하며, 원격 미디어 origin과 API origin의 직접 재생은 허용하지 않습니다.

---

## Production 부팅 가드

- `AFTERGLOW_ENV=production` + `AFTERGLOW_ALLOW_INSECURE=1` → **즉시 ValueError**
- `AFTERGLOW_ENV=production` + `secret_key` default 값 → **즉시 ValueError**
- dev 환경은 INSECURE=1 + default secret_key 가 경고만 (부팅 허용)

---

## 알려진 제한 / 후속 작업

| 항목 | 우선도 | PR 후보 |
|---|---|---|
| sessionStorage 자격은 JavaScript-readable이며 탭 복제 시 복사될 수 있음 (localStorage persistence 제거) | 잔여 방어 한계 | HttpOnly BFF 설계 별도 |
| script nonce/hash 적용, dynamic style unsafe-inline 유지 | 잔여 방어 한계 | style 정책 별도 |
| K3s background task admin conn 무한 진행 (logout 무력화) | High | PR-C |
| K8s securityContext / NetworkPolicy 부재 | High | PR-E |
| `:latest` tag + ArgoCD digest pinning | High | PR-E |
| HAProxy 컨테이너 USER root | High | PR-E |
| CI dependency / image scan gate 없음 | High | PR-F |
| Manila CSI manifest 평문 admin password (worker node 노출) | Medium | PR-G |
| extend-session CSRF 보호 부재 | Medium | PR-G |
| K3s callback 토큰 IP 하드 바인딩 (현재는 logging only) | Medium | PR-C |

---

- [루트 Architecture 정본](https://github.com/openstack-afterglow/openstack-afterglow/blob/main/ARCHITECTURE.md)
- [배포](deployment.md)
