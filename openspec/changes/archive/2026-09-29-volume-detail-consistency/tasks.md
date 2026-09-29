## Implementation Tasks

- [x] Add authorized PATCH volume rename endpoint and meaningful backend ownership/validation/failure tests.
- [x] Add rename controls from the volume list and detail, refresh both surfaces after success, show request failures.
- [x] Resolve attached instance names with project isolation and a labeled UUID fallback.
- [x] Use the same volume detail component for list SlidePanel and standalone route; remove obsolete duplicate detail implementation.
- [x] Run focused and full gates plus local browser smoke comparing both routes, update storage docs and architecture stamp, archive this change when complete.
