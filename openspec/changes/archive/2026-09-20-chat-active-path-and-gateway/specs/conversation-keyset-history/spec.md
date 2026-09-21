## ADDED Requirements

### Requirement: Message history uses opaque bidirectional keyset cursors
`GET /v1/conversations/{conversation_id}/messages` SHALL accept `limit` and at most one opaque `before` or `after` cursor. With no cursor it SHALL return the newest active-path page; `before` SHALL return the immediately older page; `after` SHALL return the immediately newer page. Every page SHALL be ordered root-to-leaf.

#### Scenario: Initial newest page
- **WHEN** the active path contains more messages than the requested limit and no cursor is supplied
- **THEN** the response contains the newest page, indicates older data exists, and reports that no newer page exists

#### Scenario: Load in both directions
- **WHEN** a client requests older data with `before` and later requests newer data with `after`
- **THEN** the pages are adjacent, stably ordered, and contain no duplicate projected message

### Requirement: Cursors are scoped, signed, and membership-checked
A cursor SHALL be opaque to clients and SHALL bind its version, conversation, projected message, and position with a server-verified signature. Malformed, tampered, cross-conversation, stale, or non-member cursors SHALL be rejected without disclosing another conversation's existence.

#### Scenario: Tampered cursor
- **WHEN** a client changes any cursor payload byte without a matching signature
- **THEN** the server rejects the cursor and returns no message data

#### Scenario: Branch switch invalidates anchor
- **WHEN** a cursor anchors a message that is no longer on the active projection after a branch switch
- **THEN** the server returns an explicit stale-cursor conflict and the client can reload without a cursor

### Requirement: Page metadata states both edges
The response SHALL expose `before`, `after`, `has_more_before`, `has_more_after`, and `at_live_edge` in addition to messages, active leaf, and initial branch metadata. Numeric ancestor cursor fields SHALL NOT remain in the contract.

#### Scenario: Middle page
- **WHEN** a page has projected messages on both sides
- **THEN** both cursors are present, both `has_more` directions are true, and `at_live_edge` is false

### Requirement: Browser history remains bounded and position-stable
Afterglow SHALL keep at most 160 decrypted message payloads for one conversation, deduplicate by stable ID, preserve viewport position when prepending, and load newer pages before claiming or scrolling to the live edge.

#### Scenario: Prepend older page
- **WHEN** older messages are inserted above the visible anchor
- **THEN** the anchor remains at the same viewport position after rendering

#### Scenario: Window exceeds bound
- **WHEN** a prepend or append would retain more than 160 messages
- **THEN** the opposite edge is evicted only when it remains recoverable through a cursor and the retained window never exceeds the bound

#### Scenario: Stream while reading history
- **WHEN** new stream deltas arrive while the reader is away from the live edge
- **THEN** the transcript does not steal scroll position and the live-edge control indicates newer content
