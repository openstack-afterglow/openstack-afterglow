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
| `GET /api/v1/chat/admin/quotas` | `/v1/admin/quotas` | 관리자: 사용자 지갑의 월·주간 쿼터와 현재 사용량 목록 |
| `PUT /api/v1/chat/admin/quotas/{user_id}` | `/v1/admin/quotas/{user_id}` | 관리자: 사용자 월·주간 쿼터 설정(`null`은 무제한) |
| `GET /api/v1/chat/mcp-oauth/callback` | `/v1/mcp-oauth/callback` | MCP OAuth 브라우저 콜백 전달 |

### Context 사용량과 압축

작성창은 lifetime 청구 token이 아니라 선택 모델에 실제로 보낼 입력의 context 점유율을 표시합니다. 입력 예산은 모델 context limit에서 응답 token reserve와 안전 reserve를 뺀 값입니다. 70%부터 이전 대화 요약을 권고하고 80% 이상이면 다음 provider 호출 전에 Lumen이 자동 압축을 시도합니다. 사용자는 작성창의 **압축**으로 같은 작업을 먼저 실행하거나 진행 중인 수동 압축을 중단할 수 있습니다.

압축은 저장되거나 화면에 보이는 메시지를 삭제하지 않습니다. Lumen이 이전 active-branch prefix의 암호화 summary checkpoint를 만들고 후속 모델 입력에서만 summary와 최근 원문을 사용합니다. `run_kind="compaction"`은 일반 응답 bubble을 만들지 않으며 완료·실패·취소 상태는 기존 run SSE로 전달됩니다. 알 수 없는 context limit/tokenizer는 0%로 추정하지 않고 사용 불가 상태로 표시합니다.

신규 저장 대화는 `title: null`로 즉시 history에 나타납니다. 첫 정상 user/assistant 교환 뒤 의미 기반 제목을 한 번 생성하고, 이후 일반 turn에서는 재생성하지 않습니다. 제목은 성공한 conversation compaction에서만 전체 누적 active path를 반영해 다시 정하며 실패·취소 시 기존 제목을 유지합니다.

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

채팅 설정은 채팅 화면 위의 팝업이다. 사이드바 사용자 메뉴의 **설정** 또는 작성창의 사용량 명령으로 열고, 팝업 안에서 사용량·API 키·메모리·MCP·도구·스킬 탭을 전환한다. MCP OAuth 복귀용 `/dashboard/chat/settings?section=mcp` deep link도 채팅 화면과 MCP 탭 팝업을 함께 연다. **API 키 → 연결 방법**에서 SDK별 `base_url`을 확인한다. 화면은 인증된 `GET /api/v1/chat/compat` BFF를 통해 Lumen의 `GET /v1/compat` 응답을 조회한다.

- OpenAI: `endpoints.openai.sdk_base_url`을 그대로 사용한다. `/v1`이 포함된다.
- Anthropic: `endpoints.anthropic.sdk_base_url`을 그대로 사용한다. SDK가 `/v1/messages`를 붙이므로 직접 `/v1`을 추가하지 않는다.
- 대시보드 호스트 앞에 `api.`를 붙여 추측하지 않는다. localhost에서 실행하는 Afterglow도 연결된 Lumen의 공개 주소를 사용한다.
- Discovery 조회 실패 시 화면은 주소를 추측하지 않고 오류와 재시도를 표시한다.

2026-09-06 실제 SDK로 확인한 DMSLab 배포 주소:

| 용도 | URL |
| --- | --- |
| Discovery | `https://lumen.dmslab.re.kr/v1/compat` |
| OpenAI `base_url` | `https://lumen.dmslab.re.kr/v1` |
| Anthropic `base_url` | `https://lumen.dmslab.re.kr` |

이 표는 해당 배포의 검증 결과다. 다른 배포는 자신의 Lumen discovery 응답을 따른다. Lumen의 공개 주소 설정, ingress 및 인증서가 서로 일치해야 한다.

> 과거 안내 주소 `https://api.cloud.dmslab.re.kr/v1`은 이 배포에서 사용하지 않는다. 실제 서버 인증서의 `*.dmslab.re.kr`은 `lumen.dmslab.re.kr`은 포함하지만 두 단계 하위 이름인 `api.cloud.dmslab.re.kr`은 포함하지 않는다. 기존 주소는 SDK의 TLS 호스트 검증에서 `APIConnectionError`로 실패했다. `verify=False`로 우회하지 않는다.

### API 키와 모델 ID

1. 채팅 화면의 **설정 → API 키**에서 발급한다. OAuth·자동화용 `/dashboard/chat/settings?section=apikeys` deep link도 같은 팝업을 연다. 평문 키는 발급 직후 한 번만 표시한다. 같은 화면에서 키 이름을 바꾸고(`PATCH /api/v1/chat/api-keys/{id}`) 월·주간 한도를 설정한다(`PATCH /api/v1/chat/api-keys/{id}/limits`, 빈 값은 해제). 한도는 본인 쿼터(`system_monthly_credit_limit`, `system_weekly_credit_limit`) 이하만 저장되고 초과 입력은 요청 전에 인라인 오류로 막는다.
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
| Discovery | `GET /v1/compat` | SDK별 연결 정보, 인증 scope, 기능 안내 |
| OpenAI | `GET /v1/models` | API 키로 사용 가능한 모델 조회 |
| OpenAI | `POST /v1/chat/completions` | 일반·스트리밍 completion |
| Anthropic | `POST /v1/messages` | 일반·스트리밍 completion |

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

### 실제 검증 기록

2026-09-06, `LUMEN_TEST_API_KEY` 및 `gpt-5.6-luna`로 TLS 검증을 유지하고 확인했다.

- OpenAI SDK 3.8.0: 모델 목록 HTTP 200, 일반 completion HTTP 200 및 시 응답, 스트리밍 HTTP 200 및 `finish_reason="stop"`/usage.
- Anthropic SDK 1.4.0: 일반 completion HTTP 200, 스트리밍 완료 및 `stop_reason="end_turn"`.
- 수정된 Afterglow 설정 화면에서 렌더링된 두 Python 예제를 그대로 추출해 실행했으며 모두 실제 응답을 출력했다.
- 2026-09-08 합성 provider HTTP 경계에서 OpenAI·Anthropic SDK 요청이 공개 ID와 `provider="perplexity"`를 Lumen resolver에 전달하고 Perplexity Agent API `/v1/responses` transport로 실행되며 응답 model은 공개 ID를 유지함을 확인했다. 실제 provider credential이나 외부 배포는 사용하지 않았다.
- 키 발급·폐기나 서버 배포 설정 변경 없이 검증했다.
