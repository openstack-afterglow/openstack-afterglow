#!/bin/sh
# Usage: sh curl.sh <operation>
set -eu
: "${LUMEN_API_KEY:?Set LUMEN_API_KEY}"
: "${LUMEN_BASE_URL:?Set LUMEN_BASE_URL}"
root=${LUMEN_BASE_URL%/}
prompt='Explain what an API gateway does in one sentence.'

case "${1:-}" in
  openai-list) curl --fail-with-body --silent --show-error "$root/v1/models" -H "Authorization: Bearer $LUMEN_API_KEY" ;;
  openai-chat)
    curl --fail-with-body --silent --show-error "$root/v1/chat/completions" \
      -H "Authorization: Bearer $LUMEN_API_KEY" -H 'Content-Type: application/json' \
      -d "{\"model\":\"${LUMEN_OPENAI_MODEL:?Set LUMEN_OPENAI_MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"$prompt\"}]}" ;;
  openai-provider)
    curl --fail-with-body --silent --show-error "$root/v1/chat/completions" \
      -H "Authorization: Bearer $LUMEN_API_KEY" -H 'Content-Type: application/json' \
      -H "X-Lumen-Provider: ${LUMEN_PROVIDER:?Set LUMEN_PROVIDER}" \
      -d "{\"model\":\"${LUMEN_MODEL:?Set LUMEN_MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"$prompt\"}]}" ;;
  openai-embed)
    curl --fail-with-body --silent --show-error "$root/v1/embeddings" \
      -H "Authorization: Bearer $LUMEN_API_KEY" -H 'Content-Type: application/json' \
      -d "{\"model\":\"${LUMEN_OPENAI_EMBED_MODEL:?Set LUMEN_OPENAI_EMBED_MODEL}\",\"input\":\"$prompt\"}" ;;
  anthropic-list)
    curl --fail-with-body --silent --show-error "$root/v1/models" \
      -H "x-api-key: $LUMEN_API_KEY" -H 'anthropic-version: 2023-06-01' ;;
  anthropic-message)
    curl --fail-with-body --silent --show-error "$root/v1/messages" \
      -H "x-api-key: $LUMEN_API_KEY" -H 'anthropic-version: 2023-06-01' -H 'Content-Type: application/json' \
      -d "{\"model\":\"${LUMEN_CLAUDE_MODEL:?Set LUMEN_CLAUDE_MODEL}\",\"max_tokens\":256,\"messages\":[{\"role\":\"user\",\"content\":\"$prompt\"}]}" ;;
  gemini-list) curl --fail-with-body --silent --show-error "$root/v1beta/models" -H "x-goog-api-key: $LUMEN_API_KEY" ;;
  gemini-generate)
    curl --fail-with-body --silent --show-error "$root/v1beta/models/${LUMEN_GEMINI_MODEL:?Set LUMEN_GEMINI_MODEL}:generateContent" \
      -H "x-goog-api-key: $LUMEN_API_KEY" -H 'Content-Type: application/json' \
      -d "{\"contents\":[{\"role\":\"user\",\"parts\":[{\"text\":\"$prompt\"}]}]}" ;;
  gemini-stream)
    curl --fail-with-body --silent --show-error --no-buffer \
      "$root/v1beta/models/${LUMEN_GEMINI_MODEL:?Set LUMEN_GEMINI_MODEL}:streamGenerateContent?alt=sse" \
      -H "x-goog-api-key: $LUMEN_API_KEY" -H 'Content-Type: application/json' \
      -d "{\"contents\":[{\"role\":\"user\",\"parts\":[{\"text\":\"$prompt\"}]}]}" ;;
  gemini-embed)
    curl --fail-with-body --silent --show-error "$root/v1beta/models/${LUMEN_GEMINI_EMBED_MODEL:?Set LUMEN_GEMINI_EMBED_MODEL}:embedContent" \
      -H "x-goog-api-key: $LUMEN_API_KEY" -H 'Content-Type: application/json' \
      -d "{\"content\":{\"parts\":[{\"text\":\"$prompt\"}]}}" ;;
  *)
    echo 'Choose openai-list, openai-chat, openai-provider, openai-embed, anthropic-list, anthropic-message, gemini-list, gemini-generate, gemini-stream, or gemini-embed.' >&2
    exit 2 ;;
esac
printf '\n'
