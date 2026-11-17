# embedding-studio Specification

## Purpose
TBD - created by archiving change lumen-embedding-studio. Update Purpose after archive.
## Requirements
### Requirement: Authorized embedding model selection
The dashboard SHALL list only Lumen embedding models and SHALL gate embedding requests on the authenticated user's current `lumen-chat_user` capability and the selected model's current `embeddings` availability and pricing gates.

#### Scenario: Permission is unavailable
- **WHEN** the capability is missing, denied, stale, or still being rechecked
- **THEN** the UI SHALL NOT submit embedding input and SHALL not present the model as ready

### Requirement: Embedding model administration
The Lumen administrator model registry SHALL expose embedding as a distinct model kind for supported direct OpenAI/Gemini API-key providers. The editor SHALL present input-token pricing only and SHALL NOT require an output-token price or media reservation.

#### Scenario: Register an embedding model
- **WHEN** an administrator selects embedding and supplies provider/model identity with an input price
- **THEN** the registry SHALL create the inactive embedding model without adding media token rates or output-price requirements

### Requirement: Embedding playground
The dashboard SHALL provide an Embedding Studio that accepts 1–16 text inputs, optional dimensions only when the selected model supports them, and a cancellable embedding request through the session-authenticated Lumen proxy.

#### Scenario: Embed and inspect vectors
- **WHEN** a successful request returns one valid vector per input
- **THEN** the UI SHALL show vector length, norm, a bounded preview, expandable full values, token/cost metadata, copy/download actions, and cosine similarity when at least two inputs exist

#### Scenario: Invalid or obsolete response
- **WHEN** response shape, dimensions, index order, or numeric values are invalid, or request ownership changes before completion
- **THEN** the UI SHALL reject the response and not render stale vector results

### Requirement: Private browser transport
Embedding requests SHALL use the authenticated Lumen BFF, and successful or handled-failure responses SHALL not be cached. The browser SHALL never receive provider credentials.

#### Scenario: Requests do not persist or cache
- **WHEN** the dashboard submits text and receives a success or handled failure through the Lumen BFF
- **THEN** the BFF SHALL use authenticated session scope, return `Cache-Control: no-store`, and never expose provider credentials

