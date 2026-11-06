## Context
The instance detail controller already classifies attached volumes by delete_on_termination.
## Decisions
Extend the existing confirmation dialog with optional exact-match text and a visible localized label. Store acceptance also checks the value; cancellation and reopening clear input. Consumer/admin share the controller. Preserve scope and lifecycle guards and ordinary confirmations.
## Risks
Cloud attachment settings can change remotely after observation; this UI is not a native transaction or authorization boundary.
