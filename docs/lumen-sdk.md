---
title: Lumen API를 SDK로 사용하기
lang: ko
nav_order: 4
permalink: /lumen-sdk.html
---

# Lumen API를 SDK로 사용하기

**Language:** 한국어 · [English](en/lumen-sdk.md)

Lumen은 공식 OpenAI SDK, Anthropic SDK, Google GenAI SDK가 호출하는 HTTP 형식을 제공한다. 이 문서는 Afterglow 대시보드에서 키를 발급하고 세 SDK를 Python·JavaScript·curl로 호출하는 방법을 설명한다. 같은 예제를 [`examples/lumen-sdk`](https://github.com/openstack-afterglow/openstack-afterglow/tree/main/docs/examples/lumen-sdk)에서 실행할 수 있다.

## 시작 전 확인

| 항목 | 값 |
| --- | --- |
| Lumen 기본 주소 (`LUMEN_BASE_URL`) | 배포의 공개 Lumen 주소. DMSLab 배포는 `https://lumen.dmslab.re.kr` |
| OpenAI SDK `base_url` | `${LUMEN_BASE_URL}/v1` |
| Anthropic SDK `base_url` | `${LUMEN_BASE_URL}` (SDK가 `/v1/messages`를 붙인다) |
| Google GenAI SDK | `base_url=${LUMEN_BASE_URL}`, `api_version="v1beta"` |
| API 키 | 대시보드에서 발급한 전체 `sk-afgl-…` 값 |

대시보드의 **채팅 설정 → API 키 → SDK 예제**는 이 배포에 설정된 Lumen 공개 주소를 미리 채운 예제를 보여 준다. 주소가 설정되지 않은 배포에서는 이 패널이 표시되지 않는다. 대시보드 주소 앞에 `api.`를 붙여 Lumen 주소를 추측하지 않는다.

## 키 발급과 과금

1. 대시보드에서 **채팅 설정 → API 키**를 연다.
2. 개인 키는 **새 API 키**로 발급한다. 도메인 관리자는 같은 화면의 **서비스 키**에서 **새 서비스 키**를 발급할 수 있다.
3. **권한**에서 **허용된 모든 권한**을 고르거나 **권한 선택**으로 아래 표의 권한을 모두 체크한다. 이 튜토리얼의 모든 예제를 실행하려면 `models:read`, `compat:completions:write`, `embeddings:write`, `compat:images:write`가 필요하다. 음성 API를 쓰려면 `compat:audio:write`도 추가한다. 권한은 발급 후 바꿀 수 없으므로 부족하면 새 키를 발급한다.

   | 대시보드 권한 | scope | 이 문서의 예제 |
   | --- | --- | --- |
   | 모델 조회 | `models:read` | OpenAI·Anthropic·Gemini `models.list`, `curl.sh *-list` |
   | 텍스트 생성 | `compat:completions:write` | OpenAI chat·responses·stream·provider 선택, Anthropic messages·stream, Gemini `generate_content`·stream |
   | 임베딩 | `embeddings:write` | OpenAI `embeddings`, Gemini `embed_content` (`:embedContent`, `:batchEmbedContents`) |
   | 이미지 생성 | `compat:images:write` | OpenAI `images.generate` |
   | 음성 생성·전사 | `compat:audio:write` | `/v1/audio/speech`, `/v1/audio/transcriptions` (이 문서에는 예제 없음) |

   현재 역할로 허용되지 않은 권한은 발급 화면에 표시되지 않는다. 필요한 권한이 없으면 프로젝트 또는 도메인 관리자에게 Lumen 권한을 요청한다.
4. 발급 직후 한 번만 표시되는 전체 키를 안전한 곳에 보관한다. 목록의 접두사만으로는 인증할 수 없다.

| 키 종류 | 소유자 | 청구 대상 |
| --- | --- | --- |
| 개인 키 | 발급한 사용자 | 사용자 지갑과 사용자 한도 |
| 서비스 키 | 도메인 | 도메인 선불 크레딧 풀, 관리자 월 한도, 시스템 상한 |

두 키 모두 **모델 API 전용**이다. 모델 조회·채팅·임베딩·이미지·오디오·실시간·의사결정처럼 허용된 모델 호출만 할 수 있다. OpenStack 클라우드 도구, 서버 도구, 대화 기록, Agent Vault/메모리, 키 관리에는 사용할 수 없다. 대시보드 전용 가상 모델 `model=lumen`도 키로 호출할 수 없다.

> **Perplexity Sonar 등 웹 검색 모델은 대시보드 채팅에서만 사용할 수 있다.** 이 모델은 Lumen의 웹 검색 도구 권한이 필요하며 모델 전용 API 키는 이 권한을 가질 수 없다. 키로 조회하는 모델 목록(`/v1/models`, `/v1beta/models`)에는 표시되지 않고, 키로 호출하면 크레딧 차감이나 provider 호출 전에 `403 model_requires_server_tools`로 거부된다.

## 환경 변수

키는 셸 기록에 남지 않게 숨김 프롬프트로 입력한다.

```bash
printf 'Lumen API key: '; read -rs LUMEN_API_KEY; printf '\n'; export LUMEN_API_KEY
export LUMEN_BASE_URL='https://lumen.dmslab.re.kr'
```

모델 ID는 배포마다 다르다. 먼저 모델 목록을 조회한 뒤 사용할 공개 모델 ID를 고른다. 예제와 smoke runner는 다음 변수를 사용한다.

| 변수 | 용도 |
| --- | --- |
| `LUMEN_OPENAI_MODEL` | OpenAI Chat Completions·Responses 모델 |
| `LUMEN_OPENAI_EMBED_MODEL` | OpenAI 임베딩 모델 |
| `LUMEN_IMAGE_MODEL` | 이미지 생성 모델 |
| `LUMEN_CLAUDE_MODEL`, `LUMEN_CLAUDE_PROVIDER` | Claude 모델과 Lumen provider ID |
| `LUMEN_GEMINI_MODEL`, `LUMEN_GEMINI_PROVIDER` | Gemini 텍스트 모델과 Lumen provider ID |
| `LUMEN_GEMINI_EMBED_MODEL` | Gemini 임베딩 모델 |

## SDK 설치

```bash
python -m pip install openai anthropic google-genai
npm install openai @anthropic-ai/sdk @google/genai
```

예제는 Python 3.10+와 Node.js 20+를 기준으로 한다. `examples/lumen-sdk/python/requirements.txt`와 `examples/lumen-sdk/node/package.json`에 검증한 SDK 범위가 있다.

## OpenAI SDK

OpenAI SDK는 `base_url`에 `/v1`을 포함한다. 같은 클라이언트로 OpenAI 모델뿐 아니라 Lumen에 등록된 Claude·Gemini 모델도 호출할 수 있다. Perplexity Sonar 같은 웹 검색 모델은 키로 호출할 수 없다.

### Python

```python
import base64
import os
from pathlib import Path

from openai import OpenAI

client = OpenAI(api_key=os.environ["LUMEN_API_KEY"], base_url=f"{os.environ['LUMEN_BASE_URL']}/v1")
model = os.environ["LUMEN_OPENAI_MODEL"]
messages = [{"role": "user", "content": "Explain what an API gateway does in one sentence."}]

for item in client.models.list():
    print(item.id)

chat = client.chat.completions.create(model=model, messages=messages)
print(chat.choices[0].message.content)

response = client.responses.create(model=model, input="Explain what an API gateway does in one sentence.")
print(response.output_text)

with client.chat.completions.create(model=model, messages=messages, stream=True) as stream:
    for chunk in stream:
        if chunk.choices:
            print(chunk.choices[0].delta.content or "", end="", flush=True)
print()

embedding = client.embeddings.create(model=os.environ["LUMEN_OPENAI_EMBED_MODEL"], input="hello")
print(len(embedding.data[0].embedding))

image = client.images.generate(model=os.environ["LUMEN_IMAGE_MODEL"], prompt="A paper boat on still water", n=1)
Path("lumen-image.png").write_bytes(base64.b64decode(image.data[0].b64_json))
```

### JavaScript

```js
import { writeFile } from 'node:fs/promises';
import OpenAI from 'openai';

const client = new OpenAI({ apiKey: process.env.LUMEN_API_KEY, baseURL: `${process.env.LUMEN_BASE_URL}/v1` });
const model = process.env.LUMEN_OPENAI_MODEL;
const messages = [{ role: 'user', content: 'Explain what an API gateway does in one sentence.' }];

for await (const item of client.models.list()) console.log(item.id);

const chat = await client.chat.completions.create({ model, messages });
console.log(chat.choices[0].message.content);

const response = await client.responses.create({ model, input: 'Explain what an API gateway does in one sentence.' });
console.log(response.output_text);

const stream = await client.chat.completions.create({ model, messages, stream: true });
for await (const chunk of stream) process.stdout.write(chunk.choices[0]?.delta.content ?? '');

const embedding = await client.embeddings.create({ model: process.env.LUMEN_OPENAI_EMBED_MODEL, input: 'hello' });
console.log(embedding.data[0].embedding.length);

const image = await client.images.generate({ model: process.env.LUMEN_IMAGE_MODEL, prompt: 'A paper boat on still water', n: 1 });
await writeFile('lumen-image.png', Buffer.from(image.data[0].b64_json, 'base64'));
```

이미지 응답은 `b64_json`만 지원한다. `response_format="url"`은 거부된다.

### Claude·Gemini 모델 선택

같은 공개 모델 ID가 여러 provider에 등록될 수 있다. 이때 `X-Lumen-Provider` 헤더에 관리자가 등록한 provider ID를 보낸다. 헤더를 생략한 요청이 여러 경로와 일치하면 Lumen은 `409 model_route_ambiguous`로 거부한다. Chat Completions는 요청 본문의 `provider` 필드도 받지만 헤더가 SDK 공통 방식이다.

```python
result = client.chat.completions.create(
    model=os.environ["LUMEN_CLAUDE_MODEL"],
    extra_headers={"X-Lumen-Provider": os.environ["LUMEN_CLAUDE_PROVIDER"]},
    messages=messages,
)
```

```js
const result = await client.chat.completions.create(
  { model: process.env.LUMEN_GEMINI_MODEL, messages },
  { headers: { 'X-Lumen-Provider': process.env.LUMEN_GEMINI_PROVIDER } },
);
```

모델 목록도 `X-Lumen-Provider`로 한 provider만 조회할 수 있다.

### curl

```bash
curl --fail-with-body "$LUMEN_BASE_URL/v1/models" -H "Authorization: Bearer $LUMEN_API_KEY"

curl --fail-with-body "$LUMEN_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $LUMEN_API_KEY" -H 'Content-Type: application/json' \
  -H "X-Lumen-Provider: $LUMEN_CLAUDE_PROVIDER" \
  -d "{\"model\":\"$LUMEN_CLAUDE_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
```

## Anthropic SDK

Anthropic SDK의 `base_url`은 `/v1` 없는 Lumen 기본 주소다. SDK가 `x-api-key`와 `anthropic-version` 헤더를 보낸다. `anthropic-version` 헤더가 있는 `GET /v1/models`는 Messages로 호출할 수 있는 모델만 반환한다.

### Python

```python
import os

from anthropic import Anthropic

client = Anthropic(api_key=os.environ["LUMEN_API_KEY"], base_url=os.environ["LUMEN_BASE_URL"])
model = os.environ["LUMEN_CLAUDE_MODEL"]
headers = {"X-Lumen-Provider": os.environ["LUMEN_CLAUDE_PROVIDER"]}
messages = [{"role": "user", "content": "Explain what an API gateway does in one sentence."}]

for item in client.models.list():
    print(item.id)

message = client.messages.create(model=model, max_tokens=256, messages=messages, extra_headers=headers)
print("".join(block.text for block in message.content if block.type == "text"))

with client.messages.stream(model=model, max_tokens=256, messages=messages, extra_headers=headers) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
print()
```

### JavaScript

```js
import Anthropic from '@anthropic-ai/sdk';

const client = new Anthropic({ apiKey: process.env.LUMEN_API_KEY, baseURL: process.env.LUMEN_BASE_URL });
const body = {
  model: process.env.LUMEN_CLAUDE_MODEL,
  max_tokens: 256,
  messages: [{ role: 'user', content: 'Explain what an API gateway does in one sentence.' }],
};
const options = { headers: { 'X-Lumen-Provider': process.env.LUMEN_CLAUDE_PROVIDER } };

for await (const item of client.models.list()) console.log(item.id);

const message = await client.messages.create(body, options);
for (const block of message.content) if (block.type === 'text') console.log(block.text);

const stream = client.messages.stream(body, options);
for await (const event of stream) {
  if (event.type === 'content_block_delta' && event.delta.type === 'text_delta') process.stdout.write(event.delta.text);
}
```

### curl

```bash
curl --fail-with-body "$LUMEN_BASE_URL/v1/messages" \
  -H "x-api-key: $LUMEN_API_KEY" -H 'anthropic-version: 2023-06-01' -H 'Content-Type: application/json' \
  -d "{\"model\":\"$LUMEN_CLAUDE_MODEL\",\"max_tokens\":256,\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
```

`/v1/messages/count_tokens`는 Anthropic API 키 경로에서만 upstream 값을 전달한다. 다른 경로는 추정치 없이 `501 token_count_unavailable`을 반환한다.

## Google GenAI SDK (Gemini)

Google GenAI SDK는 Lumen 기본 주소(`/v1` 없음)와 `api_version="v1beta"`를 사용한다. SDK가 키를 `x-goog-api-key` 헤더로 보낸다. `X-API-Key`와 `Authorization: Bearer`도 받지만 `?key=` 쿼리는 읽지 않는다(`401`). 모델 목록의 `supportedGenerationMethods`(Python SDK의 `supported_actions`, JS SDK의 `supportedActions`)를 보고 모델을 고른다. 텍스트 모델은 `generateContent`·`streamGenerateContent`, Gemini 임베딩 모델은 `embedContent`·`batchEmbedContents`를 광고한다.

모델 이름은 공개 ID가 하나의 provider에만 있으면 `models/<공개 모델 ID>`다. 여러 provider가 같은 공개 ID를 쓰면 각각 `models/lumen/<provider_id>/<model_id>`로 나열된다. 이 이름을 그대로 `model`에 넣거나, 공개 ID와 `X-Lumen-Provider` 헤더를 함께 보낸다. 헤더 없이 모호한 공개 ID를 쓰면 `409 FAILED_PRECONDITION`이다.

### Python

```python
import os

from google import genai
from google.genai.types import HttpOptions

client = genai.Client(
    api_key=os.environ["LUMEN_API_KEY"],
    http_options=HttpOptions(base_url=os.environ["LUMEN_BASE_URL"], api_version="v1beta"),
)
model = os.environ["LUMEN_GEMINI_MODEL"]
config = {"http_options": HttpOptions(headers={"X-Lumen-Provider": os.environ["LUMEN_GEMINI_PROVIDER"]})}

for item in client.models.list():
    print(item.name, item.supported_actions)

result = client.models.generate_content(model=model, contents="Explain what an API gateway does in one sentence.", config=config)
print(result.text)

for chunk in client.models.generate_content_stream(model=model, contents="Count from one to five.", config=config):
    print(chunk.text or "", end="", flush=True)
print()

embedding = client.models.embed_content(model=os.environ["LUMEN_GEMINI_EMBED_MODEL"], contents="hello")
print(len(embedding.embeddings[0].values))
```

### JavaScript

```js
import { GoogleGenAI } from '@google/genai';

const client = new GoogleGenAI({
  apiKey: process.env.LUMEN_API_KEY,
  httpOptions: { baseUrl: process.env.LUMEN_BASE_URL, apiVersion: 'v1beta' },
});
const model = process.env.LUMEN_GEMINI_MODEL;
const config = { httpOptions: { headers: { 'X-Lumen-Provider': process.env.LUMEN_GEMINI_PROVIDER } } };

for await (const item of await client.models.list({})) console.log(item.name, item.supportedActions);

const result = await client.models.generateContent({ model, contents: 'Explain what an API gateway does in one sentence.', config });
console.log(result.text);

const stream = await client.models.generateContentStream({ model, contents: 'Count from one to five.', config });
for await (const chunk of stream) process.stdout.write(chunk.text ?? '');

const embedding = await client.models.embedContent({ model: process.env.LUMEN_GEMINI_EMBED_MODEL, contents: 'hello' });
console.log(embedding.embeddings[0].values.length);
```

### curl

```bash
curl --fail-with-body "$LUMEN_BASE_URL/v1beta/models" -H "x-goog-api-key: $LUMEN_API_KEY"

curl --fail-with-body "$LUMEN_BASE_URL/v1beta/models/${LUMEN_GEMINI_MODEL}:generateContent" \
  -H "x-goog-api-key: $LUMEN_API_KEY" -H 'Content-Type: application/json' \
  -d '{"contents":[{"role":"user","parts":[{"text":"Hello"}]}]}'

curl --fail-with-body --no-buffer "$LUMEN_BASE_URL/v1beta/models/${LUMEN_GEMINI_MODEL}:streamGenerateContent?alt=sse" \
  -H "x-goog-api-key: $LUMEN_API_KEY" -H 'Content-Type: application/json' \
  -d '{"contents":[{"role":"user","parts":[{"text":"Hello"}]}]}'
```

Gemini 지원 범위와 제한:

- 모델 목록·단일 모델 조회(`pageSize`, `pageToken`, `nextPageToken`), `generateContent`, `streamGenerateContent?alt=sse`(마지막 chunk에 `usageMetadata`), `embedContent`, `batchEmbedContents`를 지원한다.
- 모델 목록에는 Gemini 모델뿐 아니라 OpenAI·Anthropic 등 다른 공급자의 텍스트 모델도 나온다(웹 검색 도구가 필요한 Perplexity Sonar 모델 제외). Gemini provider 모델은 그대로 실행하고 다른 텍스트 모델은 변환해 실행한다. 둘 다 텍스트, inline 이미지, `systemInstruction`, function 선언(`functionCall` 응답), `temperature`, `topP`, `maxOutputTokens`, `stopSequences`, JSON 모드(`responseMimeType: application/json`)를 지원한다.
- inline 이미지 형식: Gemini 모델은 png/jpeg/webp/heic/heif, 변환 모델은 png/jpeg/webp/gif. 변환 모델에 `topK`, `safetySettings`, `thinkingConfig`, penalty, `seed`를 보내면 `400`이다.
- 요청 필드는 닫혀 있어 알 수 없는 필드는 `400`이다. 모든 모델에서 거부: 서버 도구(`googleSearch` 등), `cachedContent`, `fileData`, 오디오·비디오·PDF 입력, `candidateCount` ≠ 1, `TEXT` 이외의 `responseModalities`, `functionCallingConfig` 이외의 `toolConfig`, 가상 모델 `lumen`.
- `countTokens`는 `501 UNIMPLEMENTED`를 반환한다.
- 오류 본문은 Google 형식 `{"error":{"code","message","status"}}`다.
- 임베딩은 관리자가 등록한 Gemini 임베딩 모델만 사용한다.
- Gemini 모델 목록과 텍스트 생성은 이 경로가 포함된 Lumen 릴리스부터 동작한다. 이전 Lumen은 이 경로에 `404`를 반환하므로 OpenAI SDK 경로를 사용한다.

## 오류 처리

| 상태·코드 | 의미 | 조치 |
| --- | --- | --- |
| `401` | 키가 없거나 잘못됨, 폐기·만료됨 | 전체 키를 다시 확인하거나 새로 발급한다. |
| `403` | 키 권한 부족 | 필요한 권한으로 새 키를 발급한다. |
| `403 model_not_allowed_for_key` | 키로 쓸 수 없는 모델(예: `model=lumen`) | 모델 목록의 공개 모델 ID를 사용한다. |
| `403 model_requires_server_tools` | Perplexity Sonar 등 웹 검색 도구가 필요한 모델. OpenAI는 `code`, Anthropic은 `permission_error`, Gemini는 `PERMISSION_DENIED`와 함께 이 메시지를 반환한다 | 대시보드 채팅에서 사용한다. 키로는 호출할 수 없다. |
| `409 model_route_ambiguous` | 같은 모델 ID가 여러 provider와 일치 | `X-Lumen-Provider` 헤더를 보낸다. |
| `domain_credit_insufficient` | 서비스 키의 도메인 선불 잔액 또는 한도 부족. OpenAI 호환 응답은 `429` | 도메인 관리자 또는 시스템 관리자에게 충전·한도 조정을 요청한다. |
| `429` (그 밖) | 사용자 한도 또는 provider 속도 제한 | 사용량을 확인하고 나중에 다시 시도한다. |
| `501` | 지원하지 않는 기능(Gemini `countTokens` 등) | 해당 기능을 호출하지 않는다. |

SDK의 자동 재시도는 과금 요청을 반복할 수 있다. 예제는 `max_retries=0`/`maxRetries: 0`으로 자동 재시도를 끈다. 운영 코드에서는 idempotency와 비용을 고려해 재시도 정책을 정한다.

## 기존 `/v1/claude-gateway`와의 차이

`/v1/claude-gateway`는 기존 Claude Code 기기 인증용 별도 경로다. 인증 방식과 수명 주기가 다르며 이 문서의 SDK 예제와 섞어 쓰지 않는다. Anthropic SDK와 현재 Claude Code는 Lumen 기본 주소와 일반 API 키를 사용한다.

## 예제 실행

```bash
git clone https://github.com/openstack-afterglow/openstack-afterglow.git
cd openstack-afterglow/docs/examples/lumen-sdk
python -m pip install -r python/requirements.txt
npm --prefix node install
python smoke.py
```

`smoke.py`는 `LUMEN_API_KEY`와 `LUMEN_BASE_URL`을 읽고 각 예제를 순서대로 실행한다. 모델 변수가 없는 예제는 `SKIP`으로 표시한다. 모델 호출은 실제 크레딧을 사용하며 이미지 예제는 임시 디렉터리에 PNG를 저장한 뒤 지운다. curl 예제는 `sh curl.sh openai-list`처럼 실행한다.
