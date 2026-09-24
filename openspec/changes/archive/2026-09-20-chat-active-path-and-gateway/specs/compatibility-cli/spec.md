## ADDED Requirements

### Requirement: Lumen exposes the supported OpenAI Responses subset
The compatibility API SHALL expose `POST /v1/responses` for the documented text input, instructions, provider selection, output token, temperature, and function-tool subset. Non-streaming responses and streaming events SHALL use Responses-native shapes and the existing model resolution, quota, billing, and safe-error boundaries.

#### Scenario: Non-streaming response
- **WHEN** an authorized client sends a supported Responses request
- **THEN** the server returns a completed `response` object with native output items and usage for the resolved public model

#### Scenario: Streaming response
- **WHEN** an authorized client sets `stream=true`
- **THEN** the server emits ordered Responses SSE lifecycle and text delta events followed by exactly one terminal completed or failed event

### Requirement: Anthropic CLI traffic uses the native Messages wire protocol
The CLI SHALL send Anthropic requests to `/v1/messages` using Anthropic request blocks and SHALL parse Anthropic non-stream responses and named SSE events without translating them into an OpenAI client request.

#### Scenario: Native Anthropic stream
- **WHEN** a user runs the Messages command with streaming enabled
- **THEN** the CLI prints text from `content_block_delta` events and handles the Anthropic terminal event without waiting for an OpenAI sentinel

### Requirement: CLI supports streaming and non-streaming execution
The `lumen-chat` CLI SHALL provide `responses` and `messages` commands with explicit model, prompt/input, provider, streaming, connect timeout, and read timeout controls. The Responses command SHALL use the official Python `client.responses.create` surface.

#### Scenario: Responses SDK call
- **WHEN** a user runs a non-streaming Responses command with valid credentials
- **THEN** the CLI invokes `client.responses.create`, prints the returned output text, and exits zero

#### Scenario: Read timeout
- **WHEN** the server does not produce a response before the configured read timeout
- **THEN** the CLI stops, prints an actionable timeout message to stderr, and exits with the documented transport failure code

### Requirement: CLI failures are actionable and machine-visible
Missing, malformed, expired, or revoked credentials SHALL produce reauthorization guidance. Input/auth, transport/timeout, and API failures SHALL use stable distinct non-zero exit codes and SHALL NOT print a success payload.

#### Scenario: Expired Gateway access
- **WHEN** the API rejects an expired or revoked Gateway credential
- **THEN** the CLI points to `lumen-chat login`, does not retry indefinitely, and exits with the auth failure code
