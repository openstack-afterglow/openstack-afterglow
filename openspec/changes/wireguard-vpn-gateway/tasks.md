## Implementation Tasks

### Phase 1 — 서버 프로비저닝 + 클라이언트 관리 + 상태 모니터링

- [x] `app/models/db.py`에 `VpnServer`/`VpnClient`/`VpnNetworkAttachment` SQLAlchemy 모델 추가
- [x] `app/models/vpn.py` Pydantic 스키마 + 보안 validator(client name/CIDR/allowed_ips/dns 화이트리스트, 개행·쉘 메타문자 거부)
- [x] `app/services/k3s_crypto.py`(또는 `vpn_crypto.py`)에 `_DOMAIN_WG_CLIENT_KEY` 도메인 + encrypt/decrypt 함수 추가
- [x] `app/services/vpn_keys.py` — X25519 클라이언트 키쌍 생성(WireGuard base64 포맷)
- [x] `app/services/vpn_ipam.py` — tunnel_cidr 내 다음 가용 host IP 할당
- [x] `app/services/vpn_provisioner.py` — 테넌트 프로젝트 스코프 부팅(`get_admin_connection_for_project`), flavor `cpu.1c_2g` 이름 해석, provider 포트+FIP+SG 생성, reconcile 토큰 발급, cloud-init 렌더 및 부팅, 실패 시 롤백
- [x] `app/services/vpn_config.py` — 클라이언트 `.conf` 렌더 + 에이전트 desired-state 렌더
- [x] `app/templates/vpn_agent.yaml.j2`(+reconcile 스크립트 템플릿) — WireGuard 설치, 서버 키쌍 생성, register 콜백, systemd timer 기반 reconcile 루프(desired-state GET → wg syncconf → status POST), 모든 동적 값 `shlex_quote`
- [x] `app/api/vpn/servers.py` — `POST/GET/GET{id}/DELETE{id}` (사용자 JWT + `project_id` 소유권 검증)
- [x] `app/api/vpn/clients.py` — 클라이언트 CRUD + `.conf`/QR 다운로드 (사용자 JWT + 소유권 검증) — QR은 프론트엔드 담당(계획서 §프론트엔드), 백엔드는 `.conf` 텍스트만 제공
- [x] `app/api/vpn/agent.py` — `register`/`desired-state`/`status` (베어러 토큰, fail-closed, `token.server_id` 바인딩 검증, rate-limit)
- [x] `app/main.py` — 라우터 등록(`/api/v1/vpn/servers`, servers/clients/agent 3개) + `_AUDIT_PREFIX_MAP`에 `("/api/v1/vpn/servers", "vpn_server")` 추가
- [x] `afterglow.conf.example` `[vpn]` 섹션 + `app/config.py` `Settings` 필드 + `generate_k8s.py` configmap 동기화
- [x] `frontend/src/lib/api/vpn.ts` + `frontend/src/lib/types/vpn.ts` — API 클라이언트
- [x] `frontend/src/routes/dashboard/network/vpn/+page.svelte` — 서버 목록/생성/상세, 클라이언트 테이블, 상태 배지(`AutoRefreshControl`), `.conf`/QR 다운로드
- [x] `frontend/src/lib/components/Sidebar.svelte` — `/dashboard/network` 그룹에 VPN 메뉴 추가 (`services.vpn` 플래그로 미설정 시 숨김)
- [x] `backend/tests/test_vpn_provisioner.py` — flavor 해석, SG/포트/FIP 생성, 상태 전이, 롤백
- [x] `backend/tests/test_vpn_clients.py` — CRUD, IPAM 유일성, project_id 소유권, `.conf` 렌더
- [x] `backend/tests/test_vpn_agent.py` — register/desired-state/status 베어러 인증, 바인딩 fail-closed
- [x] `backend/tests/test_vpn_security.py` — 인젝션 회귀(개행/쉘 메타문자 거부, shlex_quote 적용 확인)
- [x] `backend/tests/test_vpn_crypto.py` — X25519 왕복, AES-GCM 도메인 분리
- [x] `app/services/neutron.py` `create_port` — security_groups를 UUID 문자열 리스트로 전달하도록 수정 (실환경 프로비저닝 400 회귀, 기존 잠복 버그)
- [x] `[services] vpn` 피처 플래그 — 관리자가 VPN 기능을 켜고 끌 수 있음 (라우터 조건부 마운트, services.vpn = 플래그 AND 설정 완료, 회귀 테스트 `test_vpn_feature_flag.py`)
- [x] `npm run test:all` + `npm run lint:backend` 모두 통과 확인
- [x] CI 설정 파일이 없는 환경에서도 Waygate 라우터 회귀 테스트가 활성화되도록 테스트 플래그 환경변수 정정

### Phase 1 마감 (운영화 · QR · 제어채널 durability · 네임스페이스 컷오버)

- [x] 🔴 에이전트 제어채널 토큰 durability 수정 — 토큰을 `waygate_servers.agent_token_encrypted`(AES-256-GCM, 도메인 `wg_agent_token`)에 영속 저장, Redis 는 캐시로만. server-scoped `hmac.compare_digest` 검증으로 변경. Redis eviction/7일 TTL 만료 후에도 채널 유지. 마이그레이션 `052_waygate_agent_token.sql`(manifest 등록), 회귀 테스트 `TestAgentTokenDurability`
- [x] QR 코드 — 프론트 `qrcode` 의존성 추가(bun.lock/package-lock.json 동기화), `getClientConfigText` 헬퍼, 클라이언트별 QR 버튼 + 모달(백엔드는 `.conf` 텍스트만 제공)
- [x] `vpn`→`waygate` 클린 컷오버 — 테스트 6종 리네임, 빈 `app/api/vpn`·`routes/.../vpn` 제거, 로그 프리픽스·사용자 대면 문자열 통일
- [x] `afterglow.conf.example [waygate]` 활성화 체크리스트 보강(callback_base_url 도달성 강조)
- [ ] ⏳ 실환경 기본 end-to-end 검증 — standalone Waygate server create → ACTIVE, client `.conf`, 실제 WireGuard handshake와 delete cleanup (실제 OpenStack + WireGuard 클라이언트 필요)

### Phase 2 — 다중 테넌트 네트워크 연결 (코드·모의 계약 완료, 실환경 검증 대기)

- [x] Waygate `waygate/api/attachments.py` — `POST/GET/DELETE /v1/servers/{server_id}/networks`와 project ownership 경계
- [x] Waygate `waygate/services/network.py` — 선택한 IPv4 `subnet_id`로 Neutron port `fixed_ips`를 제한하고 port ID로 Nova attach; 실패 rollback과 detach port 정리
- [x] desired-state `nat_networks`, 에이전트 hot-plug NIC DHCP/SNAT, 클라이언트 `.conf` `AllowedIPs` CIDR 병합 유지
- [x] Afterglow `/dashboard/network/waygate` — project-visible non-external network와 subnet `SearchSelect`, 단일 subnet 자동 선택, 빈 subnet submit 차단, 명시적 `{network_id, subnet_id, nat_mode: "snat"}` 제출
- [x] Afterglow BFF attach/list/detach 계약과 named `waygate` frontend target 추가
- [x] direct Waygate callback origin을 `WAYGATE_PUBLIC_BASE_URL`로 필수화하고 API/worker가 missing/localhost/loopback URL을 fail-closed 거부
- [x] Waygate network rollback/ownership/IPv4/callback 회귀와 기본 skip인 opt-in live lifecycle harness 추가
- [ ] ⏳ 실제 OpenStack lifecycle 검증 — create → ACTIVE → 명시 subnet attach/list/detach → delete/404 수렴
- [ ] ⏳ 실제 WireGuard data-plane 검증 — 클라이언트 handshake 후 터널로 선택 subnet 내부 인스턴스 도달(SNAT+핫플러그 NIC)

### Phase 3 — 백업 / 마이그레이션 (코드 완료)

- [x] `POST /api/v1/waygate/servers/{id}/export` — 클라이언트+네트워크 연결 번들(서버 키 제외). GET 이 아닌 POST: 패스프레이즈를 받고 래핑된 시크릿을 방출하므로. `Cache-Control: no-store`
- [x] `POST /api/v1/waygate/servers/{id}/import` — 대상 서버에 클라이언트 재생성(키 보존 → public key 무결성 대조). import 값은 기존 validator(name/CIDR/dns)로 재검증, 개별 실패는 스킵 요약
- [x] export 번들 private key 보호 방식 확정 — **3a 패스프레이즈 래핑**(scrypt→AES-256-GCM, `app/services/waygate_migration.py`). DB 마스터키 복호화 → 패스프레이즈 재래핑 → import 시 언래핑 후 대상 마스터키 재암호화. 잘못된 패스프레이즈는 GCM 인증 실패로 fail-closed. 클라이언트 키 보존 → 무중단 이전
- [x] 프론트 — `lib/api/waygate.ts` export/import + `lib/types/waygate.ts` + 상세 패널 "백업/마이그레이션" 섹션(내보내기/가져오기 모달)
- [x] `test_waygate_migration.py` — wrap/unwrap 왕복·오패스프레이즈 fail-closed, export 서버키 미포함, import 왕복 키보존·악성 이름 거부·소유권(IDOR)·패스프레이즈 최소길이
