# Lumen Embedding Studio

## Why
Lumen exposes chat, image, and audio model workflows, but users cannot test registered text-embedding models from the dashboard or use Lumen as an OpenAI/Gemini embedding endpoint.

## What changes
- Add a distinct Lumen embedding model kind and user-visible model listing/capability metadata.
- Add OpenAI-compatible `/v1/embeddings`, Gemini-compatible `/v1beta/models/{model}:embedContent` and `:batchEmbedContents`, and a Keystone-session native playground call.
- Add an Afterglow Embedding Studio with model selection, bounded multi-input editing, optional dimensions, vector inspection, token/cost display and cosine comparison.
- Keep provider credentials server-side; route dashboard requests through authenticated Lumen BFF with no-store responses.

## Acceptance
- OpenAI and Google SDK clients can call their expected endpoint families with API-key authentication.
- Session-auth dashboard flow returns validated vectors for a selected model and handles cancellation, permission changes, malformed results and errors.
- Input text and vectors are not persisted by the dashboard; provider usage and cost settle through Lumen's existing ledger.
- Tests, architecture/docs and verification records reflect actual source/runtime evidence; fake-provider results are not reported as live-provider or production acceptance.
