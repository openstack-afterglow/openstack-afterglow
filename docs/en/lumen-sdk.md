---
title: Using the Lumen API with SDKs
parent: English
lang: en
nav_order: 3
permalink: /en/lumen-sdk.html
---

# Using the Lumen API with SDKs

**Language:** [한국어](../lumen-sdk.md) · English

Lumen serves the HTTP formats used by the official OpenAI SDK, Anthropic SDK and Google GenAI SDK. This guide shows how to issue a key in the Afterglow dashboard and call the three SDKs from Python, JavaScript and curl. The same examples are runnable from [`examples/lumen-sdk`](https://github.com/openstack-afterglow/openstack-afterglow/tree/main/docs/examples/lumen-sdk).

## Before you start

| Item | Value |
| --- | --- |
| Lumen root URL (`LUMEN_BASE_URL`) | The deployment's public Lumen URL. The DMSLab deployment uses `https://lumen.dmslab.re.kr` |
| OpenAI SDK `base_url` | `${LUMEN_BASE_URL}/v1` |
| Anthropic SDK `base_url` | `${LUMEN_BASE_URL}` (the SDK appends `/v1/messages`) |
| Google GenAI SDK | `base_url=${LUMEN_BASE_URL}`, `api_version="v1beta"` |
| API key | The complete `sk-afgl-…` value issued in the dashboard |

**Chat settings → API keys → SDK examples** in the dashboard shows examples prefilled with the public Lumen URL configured for that deployment. The panel is hidden when no URL is configured. Do not guess the Lumen URL by adding `api.` to the dashboard host.

## Keys and billing

1. Open **Chat settings → API keys** in the dashboard.
2. Issue a personal key with **New API key**. Domain managers can issue a key under **Service keys** with **New service key**.
3. Under **Permissions**, choose **All allowed** or select every permission in the table below with **Restricted**. Running every example in this guide needs `models:read`, `compat:completions:write`, `embeddings:write` and `compat:images:write`. Add `compat:audio:write` for the audio APIs. Permissions cannot be changed after issuance; issue a new key if one is missing.

   | Dashboard permission | Scope | Examples in this guide |
   | --- | --- | --- |
   | Read models | `models:read` | OpenAI, Anthropic and Gemini `models.list`, `curl.sh *-list` |
   | Generate text | `compat:completions:write` | OpenAI chat, responses, stream and provider selection; Anthropic messages and stream; Gemini `generate_content` and stream |
   | Embeddings | `embeddings:write` | OpenAI `embeddings`; Gemini `embed_content` (`:embedContent`, `:batchEmbedContents`) |
   | Generate images | `compat:images:write` | OpenAI `images.generate` |
   | Generate and transcribe audio | `compat:audio:write` | `/v1/audio/speech`, `/v1/audio/transcriptions` (no example in this guide) |
   | Decisions | `decisions:write` | `/v1/decisions`, `/v1/chat/decisions`, `/v1beta/decisions` (no example in this guide) |
   | Generate audio (dashboard route) | `native:audio:write` | `/v1/chat/audio/speech` (no example in this guide) |
   | Realtime audio | `compat:realtime:write` | `/v1/realtime`, `/v1/realtime/translations`, `/v1/live/sessions`, `/v1beta/realtime` WebSocket (no example in this guide) |

   The issuance form offers only the scopes returned by Lumen's issuance policy, and hides scopes your current roles do not allow. Ask a project or domain manager for the Lumen permission if one is missing. Usage reads, batches and files, conversation history and memory, and server tool execution cannot be issued to API keys. Function tools your client defines in a request (function calling) are allowed; server-side or hosted tools such as web search, code execution, MCP and cloud tools are not.
4. Store the complete key shown once after issuance. The prefix in the list cannot authenticate.

| Key type | Owner | Billed to |
| --- | --- | --- |
| Personal key | The issuing user | The user's wallet and user limits |
| Service key | The domain | The domain's prepaid credit pool, manager monthly limit and system ceiling |

Both key types are **model-API only**. They can call permitted model operations such as model listing, chat, embeddings, images, audio, realtime and decisions. They cannot use OpenStack cloud tools, server tools, conversation history, Agent Vault/memory or key management. The dashboard-only virtual model `model=lumen` is not available to keys.

> **Perplexity Sonar and other web-search models are available only in dashboard chat.** They need Lumen's web-search tool permission, which model-only API keys cannot hold. They are hidden from key model lists (`/v1/models`, `/v1beta/models`), and key requests to them are rejected with `403 model_requires_server_tools` before any credit hold or provider call.

## Environment variables

Read the key from a hidden prompt so it does not enter shell history.

```bash
printf 'Lumen API key: '; read -rs LUMEN_API_KEY; printf '\n'; export LUMEN_API_KEY
export LUMEN_BASE_URL='https://lumen.dmslab.re.kr'
```

Model IDs differ between deployments. List the models first, then choose public model IDs. The examples and the smoke runner use these variables.

| Variable | Purpose |
| --- | --- |
| `LUMEN_OPENAI_MODEL` | OpenAI Chat Completions and Responses model |
| `LUMEN_OPENAI_EMBED_MODEL` | OpenAI embedding model |
| `LUMEN_IMAGE_MODEL` | Image generation model |
| `LUMEN_CLAUDE_MODEL`, `LUMEN_CLAUDE_PROVIDER` | Claude model and Lumen provider ID |
| `LUMEN_GEMINI_MODEL`, `LUMEN_GEMINI_PROVIDER` | Gemini text model and Lumen provider ID |
| `LUMEN_GEMINI_EMBED_MODEL` | Gemini embedding model |

## Install the SDKs

```bash
python -m pip install openai anthropic google-genai
npm install openai @anthropic-ai/sdk @google/genai
```

The examples target Python 3.10+ and Node.js 20+. `examples/lumen-sdk/python/requirements.txt` and `examples/lumen-sdk/node/package.json` record the checked SDK ranges.

## OpenAI SDK

The OpenAI SDK `base_url` includes `/v1`. The same client can call OpenAI models and the Claude and Gemini models registered in Lumen. Web-search models such as Perplexity Sonar cannot be called with a key.

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

Image responses support `b64_json` only. `response_format="url"` is rejected.

### Selecting Claude and Gemini models

The same public model ID can be registered under more than one provider. Send the administrator-registered provider ID in the `X-Lumen-Provider` header. When a request without the header matches more than one route, Lumen rejects it with `409 model_route_ambiguous`. Chat Completions also accepts a `provider` body field, but the header works the same way in every SDK.

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

`X-Lumen-Provider` also filters the model list to one provider.

### curl

```bash
curl --fail-with-body "$LUMEN_BASE_URL/v1/models" -H "Authorization: Bearer $LUMEN_API_KEY"

curl --fail-with-body "$LUMEN_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $LUMEN_API_KEY" -H 'Content-Type: application/json' \
  -H "X-Lumen-Provider: $LUMEN_CLAUDE_PROVIDER" \
  -d "{\"model\":\"$LUMEN_CLAUDE_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
```

## Anthropic SDK

The Anthropic SDK `base_url` is the Lumen root URL without `/v1`. The SDK sends the `x-api-key` and `anthropic-version` headers. `GET /v1/models` with an `anthropic-version` header lists only models callable through Messages.

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

`/v1/messages/count_tokens` forwards the upstream value only on Anthropic API-key routes. Other routes return `501 token_count_unavailable` instead of an estimate.

## Google GenAI SDK (Gemini)

The Google GenAI SDK uses the Lumen root URL (no `/v1`) with `api_version="v1beta"`. The SDK sends the key in the `x-goog-api-key` header. `X-API-Key` and `Authorization: Bearer` also work, but the `?key=` query is not read (`401`). Choose models by `supportedGenerationMethods` (the Python SDK's `supported_actions`, the JS SDK's `supportedActions`). Text models advertise `generateContent` and `streamGenerateContent`; Gemini embedding models advertise `embedContent` and `batchEmbedContents`.

A model is named `models/<public model ID>` when only one provider serves that ID. When several providers share a public ID, each is listed as `models/lumen/<provider_id>/<model_id>`. Pass that name as `model`, or send the public ID with the `X-Lumen-Provider` header. An ambiguous public ID without the header returns `409 FAILED_PRECONDITION`.

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

Gemini scope and limits:

- Supported: model list and single-model get (`pageSize`, `pageToken`, `nextPageToken`), `generateContent`, `streamGenerateContent?alt=sse` (the final chunk carries `usageMetadata`), `embedContent` and `batchEmbedContents`.
- The model list includes text models from other providers such as OpenAI and Anthropic as well as Gemini models (excluding Perplexity Sonar models, which need the web-search tool). Gemini-provider models run natively; other text models are translated. Both support text, inline images, `systemInstruction`, function declarations (returned as `functionCall`), `temperature`, `topP`, `maxOutputTokens`, `stopSequences` and JSON mode (`responseMimeType: application/json`).
- Inline image types: png/jpeg/webp/heic/heif for Gemini models, png/jpeg/webp/gif for translated models. `topK`, `safetySettings`, `thinkingConfig`, penalties and `seed` return `400` on translated models.
- The request schema is closed; unknown fields return `400`. Rejected for every model: server tools (`googleSearch` and similar), `cachedContent`, `fileData`, audio/video/PDF input, `candidateCount` other than 1, `responseModalities` other than `TEXT`, `toolConfig` other than `functionCallingConfig`, and the virtual `lumen` model.
- `countTokens` returns `501 UNIMPLEMENTED`.
- Error bodies use the Google shape `{"error":{"code","message","status"}}`.
- Embeddings use only the Gemini embedding models registered by an administrator.
- Gemini model listing and text generation require a Lumen release that includes these routes. Older Lumen releases return `404` on them; use the OpenAI SDK path there.

## Errors

| Status / code | Meaning | Action |
| --- | --- | --- |
| `401` | Missing, invalid, revoked or expired key | Check the complete key or issue a new one. |
| `403` | Missing key permission | Issue a new key with the required permissions. |
| `403 model_not_allowed_for_key` | Model unavailable to keys (for example `model=lumen`) | Use a public model ID from the model list. |
| `403 model_requires_server_tools` | Perplexity Sonar or another model that needs the web-search tool. OpenAI returns it as `code`, Anthropic as a `permission_error` message, Gemini with `PERMISSION_DENIED` | Use it in dashboard chat; keys cannot call it. |
| `409 model_route_ambiguous` | The model ID matches more than one provider | Send the `X-Lumen-Provider` header. |
| `domain_credit_insufficient` | The service key's domain prepaid balance or limit is exhausted. OpenAI-compatible responses use `429` | Ask a domain manager or system administrator for a top-up or limit change. |
| `429` (other) | User limit or provider rate limit | Check usage and retry later. |
| `501` | Unsupported feature (such as Gemini `countTokens`) | Do not call that feature. |

Automatic SDK retries can repeat billed requests. The examples disable them with `max_retries=0` / `maxRetries: 0`. Choose a production retry policy with idempotency and cost in mind.

## Difference from legacy `/v1/claude-gateway`

`/v1/claude-gateway` is a separate path for the legacy Claude Code device authorization. Its authentication and lifecycle differ, so do not mix it with these SDK examples. The Anthropic SDK and current Claude Code use the Lumen root URL with an ordinary API key.

## Run the examples

```bash
git clone https://github.com/openstack-afterglow/openstack-afterglow.git
cd openstack-afterglow/docs/examples/lumen-sdk
python -m pip install -r python/requirements.txt
npm --prefix node install
python smoke.py
```

`smoke.py` reads `LUMEN_API_KEY` and `LUMEN_BASE_URL`, then runs each example in order. It prints `SKIP` for examples whose model variables are unset. Model calls spend real credit; the image example writes its PNG to a temporary directory that is removed afterwards. Run curl examples as `sh curl.sh openai-list`.
