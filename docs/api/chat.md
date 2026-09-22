---
title: 채팅 (Chat)
parent: API 레퍼런스
nav_order: 64
---

# 채팅 (Chat) API (Lumen AI API 프록시)

> 태그: `chat`
> 기본 경로: `/api/v1/chat`

Afterglow 백엔드는 독자적인 AI 모델 실행 엔진, LiteLLM 라우팅, LangGraph/LangChain 에이전트 런타임 및 공급자 API 키를 포함하지 않으며, 외부 **Lumen AI API** 서비스의 인증된 **BFF(Backend-For-Frontend) 프록시** 역할을 수행합니다.

직접적인 OpenAI / Anthropic 호환 API 호스팅은 Lumen 서비스가 전담합니다.

> **활성화 조건:** `afterglow.conf [services] chat = true` 및 `[services] lumen_internal_url` (또는 Keystone 서비스 카탈로그).
> 비활성화 상태에서는 `/api/v1/chat` 라우터가 마운트되지 않습니다.

---

## 인증 방식

### 1. 사용자 세션 인증 (Browser BFF Routes)
웹 프론트엔드의 모든 `/api/v1/chat/*` 엔드포인트 요청은 사용자의 세션 토큰 인증이 필수입니다.

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 기본 프로젝트 사용 |

### 2. 쿠키 기반 인증 콜백 (OAuth Callback)
`GET /api/v1/chat/mcp-oauth/callback` 경로의 브라우저 리다이렉트 콜백은 Bearer 토큰 없이 상태 쿠키(`Cookie`)를 보존하여 Lumen 상위 경로로 전달합니다.

### 3. 워크로드 인증 (Delegated MCP Control-Plane Bridge)
Lumen 워크로드가 Afterglow의 MCP 제어면을 호출하는 `/api/v1/mcp/lumen/*` 경로는 워크로드 전용 공유 비밀문자열로 인증합니다.

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <LUMEN_MCP_SERVICE_TOKEN>` |

---

## 주요 프록시 엔드포인트

Afterglow 백엔드는 모든 `/api/v1/chat/{path}` 요청을 내부 Lumen 서비스 URL의 `/v1/{path}` 경로로 투명하게 위임하며, SSE(Server-Sent Events) 스트리밍 응답의 비버퍼링 전달을 보장합니다.

| 메서드 · 경로 | 상위 위임 경로 | 설명 |
|--------------|----------------|------|
| `GET /api/v1/chat/models` | `/v1/chat/models` | 사용 가능한 LLM 모델 목록 조회 |
| `GET /api/v1/chat/conversations` | `/v1/conversations` | 대화 목록 조회 |
| `POST /api/v1/chat/conversations` | `/v1/conversations` | 신규 대화 생성 |
| `GET /api/v1/chat/conversations/{id}/messages?anchor=latest\|first&limit=40` | `/v1/conversations/{id}/messages` | active-path message page; opaque `before_cursor`/`after_cursor`를 후속 `cursor` query로 그대로 전달 |
| `PATCH /api/v1/chat/conversations/{id}/active-leaf` | `/v1/conversations/{id}/active-leaf` | sibling message ID와 `descend=true`로 selected branch의 newest descendant까지 활성 경로 전환 |
| `POST /api/v1/chat/conversations/{id}/completions` | `/v1/conversations/{id}/completions` | 실행을 접수하고 `202` run descriptor 반환; 이후 events URL로 SSE 구독 |
| `POST /api/v1/chat/conversations/{id}/context-preview` | `/v1/conversations/{id}/context-preview` | 현재 모델·기능·작성 중 입력까지 반영한 context token 예산과 압축 권고를 읽기 전용으로 계산 |
| `POST /api/v1/chat/conversations/{id}/compactions` | `/v1/conversations/{id}/compactions` | `expected_context_revision`과 `Idempotency-Key`로 수동 압축 run을 접수하고 `202` descriptor 반환 |
| `POST /api/v1/chat/temp-threads/{id}/context-preview` | `/v1/temp-threads/{id}/context-preview` | 임시 대화의 context 예산을 저장 대화와 같은 규칙으로 계산 |
| `POST /api/v1/chat/temp-threads/{id}/compactions` | `/v1/temp-threads/{id}/compactions` | 임시 대화의 수동 압축 run 접수; thread 만료 시 checkpoint도 함께 삭제 |
| `GET /api/v1/chat/runs/{run_id}/events` | `/v1/runs/{run_id}/events` | 실시간 실행 이벤트 스트림 (SSE 스트리밍) |
| `POST /api/v1/chat/runs/{run_id}/cancel` | `/v1/runs/{run_id}/cancel` | 실행 중인 에이전트 중단 |
| `POST /api/v1/chat/runs/{run_id}/approvals/{call_id}` | `/v1/runs/{run_id}/approvals/{call_id}` | 사용자 승인/거절 상태 제출 |
| `GET /api/v1/chat/usage` | `/v1/usage` | 사용자 본인의 토큰 및 크레딧 사용량 조회 |
| `PATCH /api/v1/chat/api-keys/{id}` | `/v1/api-keys/{id}` | 본인 API 키 이름 변경 |
| `PATCH /api/v1/chat/api-keys/{id}/limits` | `/v1/api-keys/{id}/limits` | 본인 API 키의 월·주간 크레딧 한도 설정(`null`은 해제) |
| `GET /api/v1/chat/admin/quotas` | `/v1/admin/quotas` | 관리자: 시스템 기본 월 한도·credit 환산 정책·사용자별 상속/override와 현재 사용량 목록 |
| `PUT /api/v1/chat/admin/quotas/defaults` | `/v1/admin/quotas/defaults` | 관리자: 시스템 전체 기본 월 한도 설정(`null`은 무제한) |
| `PUT /api/v1/chat/admin/quotas/{user_id}` | `/v1/admin/quotas/{user_id}` | 관리자: 사용자 개인 월·주간 override 설정(`null`은 명시적 무제한) |
| `DELETE /api/v1/chat/admin/quotas/{user_id}` | `/v1/admin/quotas/{user_id}` | 관리자: 개인 override를 지우고 시스템 기본값 상속으로 복원 |
| `GET /api/v1/chat/admin/stats/users/{user_id}` | `/v1/admin/stats/users/{user_id}` | 관리자: 기간·모델·web/API source·timestamp/token/cost별 사용자 usage ledger |
| `PATCH /api/v1/chat/admin/providers/{provider_id}` | `/v1/admin/providers/{provider_id}` | 관리자: inference key와 별개인 direct OpenAI/Anthropic 조직 사용량 관리자 키 설정·교체·제거 |
| `GET /api/v1/chat/admin/providers/billing` | `/v1/admin/providers/billing` | 관리자: 모든 configured provider의 Lumen 귀속 일·주·월·누적 request/token/raw USD cost, OpenAI/Anthropic 공식 조직 report, OpenRouter/DeepSeek live 잔액/한도, 공식 console URL을 한 번에 조회 |
| `POST /api/v1/chat/claude-gateway/authorize` | `/v1/claude-gateway/authorize` | authenticated current user/project가 8자리 Claude Code device user code를 approve/deny |
| `GET /api/v1/chat/mcp-oauth/callback` | `/v1/mcp-oauth/callback` | MCP OAuth 브라우저 콜백 전달 |

관리자 provider 화면의 **사용량 키 설정**은 direct OpenAI API와 Anthropic API에만 표시됩니다. 이 키는 Lumen이 inference key와 다른 AES-GCM/HKDF domain으로 암호화해 저장하며 organization cost/usage report에만 사용합니다. 브라우저와 API read 응답에는 키 값 대신 설정 여부만 반환됩니다. OpenAI는 현재 UTC 일·주·월 공식 비용·요청·토큰, Anthropic은 공식 비용·토큰을 표시합니다. Anthropic 공식 report에 없는 요청 수와 현재 달 범위로 계산할 수 없는 누적값은 `—`로 표시합니다. 두 provider의 공식 organization API는 현재 선불 잔액이나 구매 충전액을 반환하지 않으므로 UI는 비용에서 잔액을 역산하지 않고 공식 결제 console을 정본으로 안내합니다.

DeepSeek의 공식 `/user/balance`는 통화별 총 account balance, 구매 충전액, 지급 credit을 제공하므로 `계정 크레딧`에 그대로 표시합니다. OpenRouter inference key의 `/api/v1/key`는 해당 key의 limit/remaining만 제공하므로 account-wide prepaid balance가 아니라 `API 키 한도`로 표시합니다. 계정 전체 구매/사용 credit API에는 별도 Management key가 필요하며 현재 Lumen credential 계약에는 포함되지 않습니다. Gemini의 선불 잔액·거래 내역은 Google AI Studio 결제 화면에서만 확인합니다. Perplexity Enterprise Computer Analytics API는 Computer 제품 분석용이므로 Sonar/API Platform 크레딧으로 표시하거나 그 key를 요청하지 않습니다. Provider별 실패와 bulk 실패는 provider CRUD를 막지 않습니다.

배포 순서는 Lumen migration `011_provider_billing_admin_key.sql` → 호환 Lumen API → Afterglow backend/frontend입니다. 구 Lumen에는 bulk `GET /v1/admin/providers/billing`보다 동적 `PATCH /v1/admin/providers/{provider_id}`만 있을 수 있어, 새 Afterglow UI의 GET이 `provider_id="billing"` route에 매칭된 뒤 HTTP 405를 반환합니다. 이 오류는 관리자 키 부족이 아니라 Afterglow/Lumen 버전 불일치입니다.

### Active-path 기록 탐색

대화 화면은 Lumen의 전체 message graph를 다운로드하거나 browser에서 parent graph를 재구성하지 않습니다. Initial/latest/first page와 cursor page는 active-path projection에 이미 root-to-leaf로 정렬되어 있으며 각 message의 `branch.previous_id`/`next_id`가 version 탐색을 제공합니다. Browser는 40개 page를 최대 3개(120 messages)만 보존합니다. **처음/이전/다음/최신**은 모든 breakpoint에서 explicit action이며 한 번 누를 때 Lumen request도 정확히 한 번 발생합니다.

이전 page prepend는 첫 visible `data-history-message-id`의 top offset을 render 전후 비교해 viewport를 보존합니다. Opposite edge page를 버려도 edge cursor가 남아 다시 가져올 수 있습니다. Selection generation, local mutation epoch, token/project와 conversation identity가 바뀐 response는 적용하지 않습니다. Branch change로 cursor revision이 stale해져 409가 오면 alert를 표시하고 latest page를 한 번만 다시 조회합니다.

사용자가 old window를 읽는 동안 run이 끝나면 transcript를 강제로 latest로 이동하지 않고 **새 응답이 도착했습니다** action을 표시합니다. Old window에서 전송하면 input을 지우기 전에 latest page를 먼저 가져와 새 turn parent를 live edge에 연결합니다. Stream draft도 old window 위에 섞지 않습니다.

### Claude Code 연결과 legacy device endpoint

현재 Claude Code 연결은 채팅 설정 **API 키 → 연결 방법**의 ordinary Anthropic API 설정을 사용합니다. `GET /api/v1/chat/compat`의 `endpoints.anthropic.sdk_base_url`을 `ANTHROPIC_BASE_URL`로, 발급한 일반 Lumen API 키를 `ANTHROPIC_AUTH_TOKEN`으로 전달하며 선택한 public model ID를 Claude model 환경 변수에 지정합니다.

`/oauth/claude/authorize`와 `/api/v1/chat/claude-gateway/authorize`는 Lumen이 구현한 기존 custom device flow 승인 화면입니다. Claude Code 2.1.278의 현재 Claude Apps Gateway login은 administrator-managed settings, 공식 gateway `/protocol`, OIDC device authorization, refresh session을 요구하므로 이 custom flow와 호환되지 않습니다. 설정 화면은 이를 Claude Code 연결 방법으로 광고하지 않습니다. 공식 Claude Apps Gateway를 별도로 배포하지 않은 환경에서는 직접 API-key 경로를 사용합니다.

### Context 사용량과 압축

작성창은 lifetime 청구 token이 아니라 선택 모델에 실제로 보낼 입력의 context 점유율을 표시합니다. 입력 예산은 모델 context limit에서 응답 token reserve와 안전 reserve를 뺀 값입니다. 70%부터 이전 대화 요약을 권고하고 80% 이상이면 다음 provider 호출 전에 Lumen이 자동 압축을 시도합니다. 사용자는 작성창의 **압축**으로 같은 작업을 먼저 실행하거나 진행 중인 수동 압축을 중단할 수 있습니다.

압축은 저장되거나 화면에 보이는 메시지를 삭제하지 않습니다. Lumen이 이전 active-branch prefix의 암호화 summary checkpoint를 만들고 후속 모델 입력에서만 summary와 최근 원문을 사용합니다. `run_kind="compaction"`은 일반 응답 bubble을 만들지 않으며 완료·실패·취소 상태는 기존 run SSE로 전달됩니다. 컨텍스트 상세 버튼은 사용/입력 예산, 남은 token과 tokenizer/추정치 구분을 키보드·터치로 보여 줍니다. 모델 한도 미확인(`context_window_unknown`), 계산 불가능한 입력(`token_count_unavailable`), 유효하지 않은 예산(`invalid_budget`)은 0% meter 없이 별도 이유를 표시합니다. 텍스트 계수 실패의 길이 기반 fallback은 `token_counter_failed` 추정치이며, preview HTTP/네트워크 실패는 오래된 용량을 지우고 정제된 오류 설명을 제공합니다.

신규 저장 대화는 `title: null`로 즉시 history에 나타납니다. 첫 정상 user/assistant 교환 뒤 durable worker가 의미 기반 제목을 한 번 생성하고, 이후 일반 turn에서는 재생성하지 않습니다. 브라우저는 서버 `title_status`를 정본으로 사용하며 30초 뒤에도 pending을 실패로 바꾸지 않고 15초 간격으로 계속 확인합니다. worker는 아직 예약되지 않은 active `auto/idle/revision=0` 대화의 완료된 첫 교환을 보수적으로 복구하며 빈 대화, 기존 job, legacy/수동/실패/삭제된 대화는 재실행하지 않습니다. 수동 제목 수정은 revision을 올려 뒤늦은 첫 요약이 덮어쓰지 못하게 합니다. 성공한 conversation compaction은 전체 누적 active path를 반영해 제목을 다시 정하며 실패·취소 시 기존 제목을 유지합니다.

### Native Search와 출처

모델 선택창은 Lumen의 `capabilities.web_search`가 참인 모델에 **Search** 배지를 표시합니다. 작성창에서는 `feature_gates.web_search`의 `mode="native"`, `available`, `pricing_available`을 함께 확인하고 선택 가능한 **Search** 버튼을 제공합니다. 구독 인증 등 지원하지 않는 경로를 모델 이름만 보고 활성화하지 않습니다.

선택한 native 검색은 completion·context-preview·regenerate 요청의 `features.web_search`에 `enabled: true`, `mode: "native"`, `provider_id: null`로 전달합니다. 검색 provider를 별도로 고르는 기존 managed 검색은 `mode: "managed"`(생략 시 기본)이며 native 요청과 섞이지 않습니다. `web_search_required` 모델은 `Search · 기본`으로 표시하고 끄는 동작을 제공하지 않습니다.

출처는 canonical `citation` part를 통해 SSE와 저장된 history에 동일하게 전달됩니다. LiteLLM Chat Completions의 `citations`/`search_results`/annotations와 Perplexity Agent의 reasoning search-result 이벤트, 완료된 search-result output item 및 최종 response output을 보존합니다. 각 assistant 답변 위에 번호·제목·도메인·반환된 snippet을 가로 목록으로 표시하고, 작은 화면에서는 목록 안에서 스크롤합니다. HTTP(S) 이외 링크는 렌더하지 않으며 입력 문서 출처에는 URL을 만들지 않습니다. 모델이 실제 출처를 반환하지 않은 답변에는 임의의 출처를 만들지 않습니다. 상단 **출처 N**은 현재 불러온 대화의 중복 제거 목록, 전체 URL/snippet 또는 정직한 빈 상태를 공통 SlidePanel로 표시합니다.

모든 화면 폭에서 채팅 영역 상단 **기록**과 **출처 N**을 사용할 수 있습니다. 모바일은 모델/에이전트와 기록/출처를 두 행으로 배치합니다. 1024px 미만의 기록은 bounded drawer, desktop은 inline sidebar이며 설정 메뉴의 기존 **채팅으로 돌아가기**와 project별 선택 복원을 유지합니다. 출처 패널은 mobile에서 full-screen modal, tablet/desktop에서 공통 비모달 panel 계약을 따릅니다. Escape/바깥 영역으로 닫으면 trigger로 focus가 복원됩니다.

가격 admission과 실행은 Lumen 소유입니다. Perplexity Agent Sonar·GLM-5.3의 공식 token 가격을 조회하며 Sonar의 Agent API와 legacy API 가격을 구분합니다. 알 수 없는 모델 가격을 0으로 처리하지 않습니다. Native Search는 기존 token 기반 크레딧 계약을 유지하므로 provider의 별도 검색 요청/툴 부가요금은 로컬 크레딧 비용에 포함되지 않습니다.

---

## 위임 MCP 제어면 브릿지 (`/api/v1/mcp/lumen`)

Lumen 서비스가 Afterglow 사용자의 MCP 도구 권한 상태를 검증하고 도구를 실행하기 위해 호출하는 제어면 API입니다.

| 메서드 · 경로 | 설명 |
|--------------|------|
| `POST /api/v1/mcp/lumen/snapshot` | 사용자/프로젝트 단위 MCP 승인 불투명 스냅샷 조회 |
| `POST /api/v1/mcp/lumen/preview` | 변개(Mutation) 도구 실행 전 제어면 사전 검증 |
| `POST /api/v1/mcp/lumen/execute` | 격리된 MCP 도구 단일 실행 및 원장(Ledger) 기록 |

---

## 외부 호환 API SDK 연결

Lumen은 외부 프로그램을 위한 OpenAI/Anthropic 호환 API를 제공한다. Afterglow는 API 키 관리 화면과 인증된 BFF를 제공하며, 모델 실행·키 검증·사용량 기록은 Lumen이 담당한다.

### 연결 주소 확인

채팅 설정은 `/dashboard/chat/settings?section=…` 전용 페이지다. 사이드바 사용자 메뉴의 **설정** 또는 작성창의 사용량 명령은 이 route로 이동하고, 사용량·API 키·메모리·MCP·도구·스킬을 desktop side navigation 및 mobile horizontal navigation으로 전환한다. MCP OAuth는 `section=mcp`, API 키 자동화는 `section=apikeys` deep link로 같은 페이지의 지정 section에 복귀한다. **API 키 → 연결 방법**은 인증된 `GET /api/v1/chat/compat` BFF를 통해 Lumen `GET /v1/compat`의 SDK/CLI별 base URL을 표시한다.

연결 방법의 Codex·Claude Code·OpenAI·Claude 선택 탭은 자체 스크롤바 없이 모두 표시된다. 모바일(`<768px`)에서는 두 열로 배치되고, 태블릿에서는 필요하면 줄바꿈한다. 긴 설정 예제 코드만 가로로 스크롤할 수 있다.

- OpenAI: `endpoints.openai.sdk_base_url`을 그대로 사용한다. `/v1`이 포함된다.
- Anthropic SDK와 Claude Code: `endpoints.anthropic.sdk_base_url`을 그대로 사용한다. client가 `/v1/messages`를 붙이므로 직접 `/v1`을 추가하지 않는다.
- Codex: `clients.codex.base_url`을 custom provider의 `base_url`로 사용하고 `wire_api = "responses"`를 선택한다. 일반 Lumen API 키를 환경 변수로 읽는다.
- 대시보드 호스트 앞에 `api.`를 붙여 추측하지 않는다. localhost에서 실행하는 Afterglow도 연결된 Lumen의 공개 주소를 사용한다. Discovery 조회 실패 시 화면은 주소를 추측하지 않고 오류와 재시도를 표시한다.

2026-09-06 실제 SDK로 확인한 DMSLab 배포 주소:

| 용도 | URL |
| --- | --- |
| Discovery | `https://lumen.dmslab.re.kr/v1/compat` |
| OpenAI `base_url` | `https://lumen.dmslab.re.kr/v1` |
| Anthropic `base_url` | `https://lumen.dmslab.re.kr` |

이 표는 해당 배포의 검증 결과다. 다른 배포는 자신의 Lumen discovery 응답을 따른다. Lumen의 공개 주소 설정, ingress 및 인증서가 서로 일치해야 한다.

> 과거 안내 주소 `https://api.cloud.dmslab.re.kr/v1`은 이 배포에서 사용하지 않는다. 실제 서버 인증서의 `*.dmslab.re.kr`은 `lumen.dmslab.re.kr`은 포함하지만 두 단계 하위 이름인 `api.cloud.dmslab.re.kr`은 포함하지 않는다. 기존 주소는 SDK의 TLS 호스트 검증에서 `APIConnectionError`로 실패했다. `verify=False`로 우회하지 않는다.

### Codex CLI (Responses)

채팅 설정 **API 키 → 연결 방법**에서 복사한 내용을 `~/.codex/config.toml`에 저장한다. `base_url`은 예시를 고정하지 않고 현재 Lumen discovery의 `clients.codex.base_url`을 그대로 표시한다.

```toml
model_provider = "lumen"
model = "replace-with-Lumen-model-ID"

[model_providers.lumen]
name = "Lumen Responses"
base_url = "https://lumen.example/v1"
env_key = "LUMEN_API_KEY"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false

# 같은 모델 ID가 여러 프로바이더에 있을 때만 설정한다.
# http_headers = { "X-Lumen-Provider" = "provider-id" }
```

`model`에는 모델 선택창의 **ID 복사** 값인 provider model ID를 넣고, 발급한 일반 API 키는 `LUMEN_API_KEY` 환경 변수로 전달한다. 설정 파일에 키를 쓰지 않는다. 같은 공개 model ID가 여러 provider에 등록된 경우에만 `X-Lumen-Provider`를 지정한다. 저장 후 `codex --strict-config`로 실행한다. Codex는 요청마다 대화 input 전체를 다시 보낼 수 있고 Lumen Responses endpoint는 이 full-input tool continuation을 처리한다.

### Claude Code CLI (Anthropic Messages)

현재 Claude Code는 Lumen의 ordinary Anthropic Messages endpoint에 일반 API 키로 직접 연결한다. API 키나 모델 ID를 설정 파일에 저장하지 않고 환경 변수로 주입한다.

```bash
export LUMEN_API_KEY="발급 직후 한 번 표시된 API 키"
export LUMEN_MODEL="모델 선택창에서 복사한 API ID"
export ANTHROPIC_BASE_URL="https://lumen.example"
export ANTHROPIC_AUTH_TOKEN="$LUMEN_API_KEY"
export ANTHROPIC_MODEL="$LUMEN_MODEL"
export ANTHROPIC_DEFAULT_SONNET_MODEL="$LUMEN_MODEL"
export ANTHROPIC_DEFAULT_OPUS_MODEL="$LUMEN_MODEL"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="$LUMEN_MODEL"

# 같은 공개 모델 ID가 여러 provider에 있을 때만 설정한다.
# export LUMEN_PROVIDER="provider-id"
# export ANTHROPIC_CUSTOM_HEADERS="X-Lumen-Provider: $LUMEN_PROVIDER"

claude
```

설정 화면의 복사 명령은 discovery가 반환한 Anthropic base URL을 그대로 사용한다. Lumen은 Claude Code가 보내는 native tool/thinking block, `context_management`, `output_config`, `anthropic-*` protocol header를 Anthropic-format provider 경계까지 보존하되 caller의 `Authorization`/`x-api-key`는 upstream provider credential로 전달하지 않는다. Current Claude Apps Gateway의 `/login`은 위 직접 API 경로와 다른 제품이며 Lumen custom device endpoint로 대체할 수 없다.

### API 키와 모델 ID

1. 채팅 화면의 **설정 → API 키** 또는 `/dashboard/chat/settings?section=apikeys` 전용 페이지에서 발급한다. 평문 키는 발급 직후 한 번만 표시한다. 같은 화면에서 키 이름을 바꾸고(`PATCH /api/v1/chat/api-keys/{id}`) 월·주간 한도를 설정한다(`PATCH /api/v1/chat/api-keys/{id}/limits`, 빈 값은 해제). 한도는 본인 쿼터 이하만 저장되고 초과 입력은 요청 전에 인라인 오류로 막는다.
2. 메시지 작성창의 **모델 선택**에서 원하는 모델 옆의 **ID 복사**를 누른다.
3. 복사되는 **API ID**는 `api_model_name`이다. 표시 이름, 내부 숫자 ID, 운영용 `model_name`/LiteLLM route가 아니며 따옴표·`model=` 접두사를 포함하지 않는다.
4. 목록의 **Provider**는 `api_provider`다. 같은 공개 API ID가 여러 provider에 있을 때 SDK 요청의 `provider` 선택자로 사용한다.
5. **ID 복사**는 선택 모델을 변경하거나 선택창을 닫지 않는다. 다음 웹 메시지의 모델을 바꾸려면 모델 이름을 선택한다.
6. 실행 환경의 `LUMEN_API_KEY`에 발급 키를, `LUMEN_MODEL`에 복사한 API ID를 설정한다. route 충돌 시 `LUMEN_PROVIDER`에 Provider를 설정한다. 키를 소스·노트북 출력·로그에 기록하지 않는다.

호환 API는 API 키를 사용하며 Keystone 토큰은 사용하지 않는다. 기본 scope는 모델 조회용 `models:read`와 completion용 `compat:completions:write`다.

- OpenAI 인증: `Authorization: Bearer <API 키>`
- Anthropic 인증: `x-api-key: <API 키>`

SDK는 `.env` 파일을 자동으로 읽지 않는다. 로컬 테스트에서 `.env`의 `LUMEN_TEST_API_KEY`를 쓰려면 예제 실행 전에 다음처럼 명시적으로 읽는다 (`python -m pip install python-dotenv` 필요).

```python
import os

from dotenv import dotenv_values

os.environ["LUMEN_API_KEY"] = dotenv_values(".env")["LUMEN_TEST_API_KEY"]
os.environ["LUMEN_MODEL"] = "gpt-5.6-luna"
# os.environ["LUMEN_PROVIDER"] = "perplexity"  # 같은 공개 ID가 여러 provider에 있을 때만
```

### Lumen 공개 엔드포인트

아래 경로는 Afterglow 대시보드 주소가 아니라 Lumen의 공개 API 주소를 기준으로 한다.

| 형식 | 메서드 · 경로 | 설명 |
| --- | --- | --- |
| Discovery | `GET /v1/compat` | SDK/Gateway별 연결 정보, 인증 scope, stream 안내 |
| OpenAI | `GET /v1/models` | API 키로 사용 가능한 모델 조회 |
| OpenAI | `POST /v1/chat/completions` | 일반·스트리밍 Chat Completions |
| OpenAI | `POST /v1/responses` | stateless Responses object와 native SSE events |
| Codex | `POST /v1/responses` | custom `responses` provider의 text·function-call·full-input continuation |
| Anthropic | `POST /v1/messages` | Anthropic-native 일반·스트리밍 Messages |
| Anthropic | `POST /v1/messages/count_tokens` | Anthropic-native input token count |
| Legacy Lumen device API | configured base의 `/oauth/device/code`, `/oauth/token`, `/v1/messages` | custom 24시간 credential protocol. Claude Code 2.1.278의 current Apps Gateway login과 호환되지 않으며 연결 가이드에 노출하지 않음 |

`GET /v1/models`의 `data[].id`가 SDK의 공개 `model` 값이고 `data[].providers`가 같은 ID를 제공하는 활성 provider type 목록이다. 모델 선택창에서 복사한 API ID와 같은 값이다. OpenAI 전용 가상 모델 `lumen`이 목록에 있다면 서버 기본 모델을 사용하는 durable 실행을 의미한다. 특정 모델을 호출하거나 Anthropic 예제를 실행할 때는 모델 선택창에서 복사한 공개 API ID를 사용하고 내부 route는 사용하지 않는다.

### 실행 가능한 Python 예제

먼저 `python -m pip install openai anthropic`으로 SDK를 설치하고 위 환경 변수를 설정한다. 아래 코드는 실제 요청을 보내며 API 사용량이 차감된다. 다른 배포에서는 `base_url`만 그 서버의 discovery 값으로 교체한다.

#### OpenAI

```python
import os

from openai import OpenAI

with OpenAI(
    base_url="https://lumen.dmslab.re.kr/v1",
    api_key=os.environ["LUMEN_API_KEY"],
) as client:
    response = client.chat.completions.create(
        model=os.environ["LUMEN_MODEL"],
        messages=[
            {"role": "user", "content": "Write a short poem about the ocean."}
        ],
        extra_body={"provider": os.environ["LUMEN_PROVIDER"]}
        if os.environ.get("LUMEN_PROVIDER")
        else None,
    )
    print(response.choices[0].message.content)
```

스트리밍은 `stream=True`로 요청한다. 선택적으로 `stream_options={"include_usage": True}`를 지정하면 마지막 usage chunk를 받을 수 있다.

```python
import os

from openai import OpenAI

with OpenAI(
    base_url="https://lumen.dmslab.re.kr/v1",
    api_key=os.environ["LUMEN_API_KEY"],
) as client:
    with client.chat.completions.create(
        model=os.environ["LUMEN_MODEL"],
        messages=[{"role": "user", "content": "Write a short poem about the ocean."}],
        stream=True,
        stream_options={"include_usage": True},
        extra_body={"provider": os.environ["LUMEN_PROVIDER"]}
        if os.environ.get("LUMEN_PROVIDER")
        else None,
    ) as stream:
        for chunk in stream:
            for choice in chunk.choices:
                print(choice.delta.content or "", end="", flush=True)
```

#### Anthropic

```python
import os

from anthropic import Anthropic

with Anthropic(
    base_url="https://lumen.dmslab.re.kr",
    api_key=os.environ["LUMEN_API_KEY"],
) as client:
    response = client.messages.create(
        model=os.environ["LUMEN_MODEL"],
        max_tokens=1024,
        messages=[
            {"role": "user", "content": "Write a short poem about the ocean."}
        ],
        extra_body={"provider": os.environ["LUMEN_PROVIDER"]}
        if os.environ.get("LUMEN_PROVIDER")
        else None,
    )
    for block in response.content:
        if block.type == "text":
            print(block.text)
```

Anthropic 스트리밍은 client가 열린 상태에서 `client.messages.stream(...)` context manager와 `stream.text_stream`을 사용한다.

### 기능 및 제한

- Provider 모델 ID의 호환 completion은 stateless 요청이다. `messages`에 필요한 대화 이력을 전달한다.
- 다른 공통 분모(타 provider)가 없는 모델(예: Perplexity 단독 제공 모델인 `sonar`, `kimi-k3`, `deepseek-v4-flash-0731`)은 `provider` 인자 없이 모델명만으로 정상 라우팅된다. 복수 provider가 동일 공개 ID를 제공하는 충돌 상황에서만 `provider` 선택자가 필수다.
- 실시간 웹 검색 기능을 지원하는 모델(예: Perplexity Agent API 및 Sonar 모델)은 요청 시 `web_search` 도구가 자동으로 활성화되어 모델이 최신 정보 검색이 필요할 때 자동으로 웹 검색을 호출한다.
- 관리자 페이지 모델 목록에서도 중복 provider 접두사가 정리된 간결한 이름과 실시간 웹 검색(`Search`) 등 기능 배지가 표시된다.
- 이미지 입력은 vision 지원 모델에서 사용한다.
- 사용량·키별 한도·월 쿼터는 Lumen 정책을 따른다. API 사용량은 웹과 분리해 집계된다.

- `max_tokens` 상한은 서버 정책을 따른다. 폐기된 키는 인증에 사용할 수 없다.
- Discovery의 공개 주소는 SDK 연결 설정이며, health 응답만으로 모델/provider 실행 성공을 판정하지 않는다.

### 관리자 quota·사용량·provider 결제 화면

`/admin/chat/quotas`는 Lumen quota envelope의 시스템 기본 월 한도와 각 사용자 개인 override를 분리해 표시한다. `기본값 복원`은 해당 지갑의 월·주간 설정만 `NULL` 상속 상태로 되돌리며 과거 usage ledger를 삭제하지 않는다. 독립 주간 ceiling이 없으면 **월 한도 내 무제한**으로 표시하지만 Lumen 월 admission은 계속 강제된다. 상단 환산 안내는 Lumen이 반환한 `credit_per_usd`, `usd_per_credit`, 공식 formula를 사용하므로 frontend 상수가 아니다.

사용자 행의 **사용량**은 modal을 열어 `7d`, `30d`, `90d`, `1y`, 전체 기간과 web/API source를 필터링한다. 모델별 및 source별 aggregate와 timestamp, 입력/출력/총 token, raw USD, 차감 credit, API key attribution이 있는 cursor ledger를 표시한다. 숫자는 Lumen immutable usage log의 projection이며 Afterglow가 별도 accounting state를 저장하지 않는다.

`/admin/chat` provider 설정은 모든 configured provider에 Lumen 귀속 일·주·월·누적 request/token/raw USD cost를 표시한다. 별도 `계정 크레딧` 영역은 DeepSeek가 공식 반환한 통화별 총 잔액·구매 충전액·지급 credit을 표시하고, OpenRouter는 inference key의 limit/remaining을 account balance와 명확히 구분한다. Direct OpenAI/Anthropic의 공식 organization report는 비용·요청·token 사용량만 제공하므로 현재 잔액이나 충전액을 사용량에서 역산하지 않고 `공식 API 조회 미지원`과 결제 console action을 표시한다. Gemini와 그 밖의 console-only provider도 같은 fail-honest 규칙을 따른다. Subscription credential, custom OpenAI-compatible base, local/unknown provider에는 오인 가능한 결제 링크를 제공하지 않는다. 결제 상태 조회 실패는 provider CRUD·실행 상태를 바꾸지 않으며 secret이나 upstream 원문 오류를 표시하지 않는다.

### 실제 검증 기록

2026-09-06, `LUMEN_TEST_API_KEY` 및 `gpt-5.6-luna`로 TLS 검증을 유지하고 확인했다.

- OpenAI SDK 3.8.0: 모델 목록 HTTP 200, 일반 completion HTTP 200 및 시 응답, 스트리밍 HTTP 200 및 `finish_reason="stop"`/usage.
- Anthropic SDK 1.4.0: 일반 completion HTTP 200, 스트리밍 완료 및 `stop_reason="end_turn"`.
- 수정된 Afterglow 설정 화면에서 렌더링된 두 Python 예제를 그대로 추출해 실행했으며 모두 실제 응답을 출력했다.
- 2026-09-08 합성 provider HTTP 경계에서 OpenAI·Anthropic SDK 요청이 공개 ID와 `provider="perplexity"`를 Lumen resolver에 전달하고 Perplexity Agent API `/v1/responses` transport로 실행되며 응답 model은 공개 ID를 유지함을 확인했다. 실제 provider credential이나 외부 배포는 사용하지 않았다.
- 2026-09-20 설치된 Codex CLI 0.154.0을 격리된 Lumen process stack과 합성 provider에 직접 연결해 text turn과 실제 `exec_command` function call, `function_call_output`을 포함한 full-input 후속 요청, 최종 응답을 확인했다. `prompt_cache_key`는 provider로 전달되고 로컬 session/turn 정보가 든 `client_metadata`는 Lumen 경계에서 제거됐다. 이는 실제 Codex wire 호환성 증거이며 live 외부 provider·Keystone 배포 증거는 아니다.
- 2026-09-20 설치된 Claude Code 2.1.278을 격리된 Lumen process stack과 합성 Anthropic provider에 직접 연결해 streaming text 응답과 실제 local `Bash` tool 실행, `tool_result` 후속 요청, 최종 `CLAUDE_TOOL_CONTINUATION_OK`를 확인했다. 최초 실행에서 422를 만든 `context_management`/`output_config` 수용과 `anthropic-*` protocol header 전달을 수정한 뒤 확인했으며, live Anthropic credential·운영 배포 증거는 아니다. 같은 버전의 current Apps Gateway login contract는 Lumen legacy device API와 호환되지 않으므로 UI의 device-login 주장을 제거했다.
- 키 발급·폐기나 서버 배포 설정 변경 없이 검증했다.
- 2026-09-16 provider credit 표시는 focused provider-page 21건과 전체 frontend 1,331건을 통과했다. 실제 Vite surface에 합성 bulk billing boundary를 연결해 light/dark 각각 390·767·768·1023·1024·1440px에서 OpenRouter key-limit provenance, DeepSeek account balance, breakpoint 전환, action 배치와 horizontal overflow 부재를 확인했다. 이는 UI/contract 증거이며 live provider credential이나 배포 검증이 아니다.
