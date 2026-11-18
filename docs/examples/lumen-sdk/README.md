# Lumen SDK examples

Runnable examples for the official OpenAI, Anthropic and Google GenAI SDKs against Lumen. The tutorial is [`docs/lumen-sdk.md`](../../lumen-sdk.md) ([English](../../en/lumen-sdk.md)).

## Setup

```bash
printf 'Lumen API key: '; read -rs LUMEN_API_KEY; printf '\n'; export LUMEN_API_KEY
export LUMEN_BASE_URL='https://lumen.dmslab.re.kr'
python -m pip install -r python/requirements.txt
npm --prefix node install
```

Issue the key in the dashboard under **Chat settings → API keys**. Personal keys bill the user; service keys bill the domain credit pool. Keys can call model APIs only. To run every example, issue the key with these scopes (or choose **All allowed**): `models:read`, `compat:completions:write`, `embeddings:write`, `compat:images:write`.

Perplexity Sonar and other web-search models are available only in dashboard chat. They need Lumen's web-search tool permission, which model-only keys cannot hold, so they are hidden from key model lists and key requests to them return `403 model_requires_server_tools`. The examples therefore cover OpenAI, Claude and Gemini models only.

Set the model variables you want to try. Pick IDs from `python python/openai_example.py list`, `python python/anthropic_example.py list` and `python python/gemini_example.py list`.

| Variable | Used by |
| --- | --- |
| `LUMEN_OPENAI_MODEL` | OpenAI chat, responses, stream |
| `LUMEN_OPENAI_EMBED_MODEL` | OpenAI embeddings |
| `LUMEN_IMAGE_MODEL` | OpenAI image generation |
| `LUMEN_CLAUDE_MODEL`, `LUMEN_CLAUDE_PROVIDER` | Anthropic messages and OpenAI provider example |
| `LUMEN_GEMINI_MODEL`, `LUMEN_GEMINI_PROVIDER` | Gemini text and OpenAI provider example |
| `LUMEN_GEMINI_EMBED_MODEL` | Gemini embeddings |

`LUMEN_CLAUDE_PROVIDER` and `LUMEN_GEMINI_PROVIDER` are optional for the native Anthropic and Gemini examples. Set them when a model ID is registered under more than one provider.

## Run

```bash
python smoke.py                  # Python and Node examples
python smoke.py --language node  # one language
python python/openai_example.py chat
node node/gemini.mjs stream
sh curl.sh gemini-generate
```

| File | Operations |
| --- | --- |
| `python/openai_example.py`, `node/openai.mjs` | `list`, `chat`, `responses`, `stream`, `embed`, `image`, `providers` |
| `python/anthropic_example.py`, `node/anthropic.mjs` | `list`, `message`, `stream` |
| `python/gemini_example.py`, `node/gemini.mjs` | `list`, `generate`, `stream`, `embed` |
| `curl.sh` | `openai-list`, `openai-chat`, `openai-provider`, `openai-embed`, `anthropic-list`, `anthropic-message`, `gemini-list`, `gemini-generate`, `gemini-stream`, `gemini-embed` |

| Scope | Operations |
| --- | --- |
| `models:read` | every `list`, `curl.sh *-list` |
| `compat:completions:write` | OpenAI `chat`, `responses`, `stream`, `providers`; Anthropic `message`, `stream`; Gemini `generate`, `stream`; `curl.sh openai-chat`, `openai-provider`, `anthropic-message`, `gemini-generate`, `gemini-stream` |
| `embeddings:write` | OpenAI `embed`, Gemini `embed`, `curl.sh openai-embed`, `gemini-embed` |
| `compat:images:write` | OpenAI `image` |

The smoke runner skips examples whose model variables are unset and exits non-zero when any example fails. Model calls spend real credit. SDK retries are disabled so a failure is not silently re-billed.
