## Implementation Tasks

- [ ] Trace the actual deployed native provider request and error against the working direct API/Codex route without replaying a production chat; document evidence, auth differences, and the correct repair location.
- [ ] Fix the confirmed OpenAI native execution incompatibility without changing durable semantics or other providers; exercise success and failure boundaries.
- [x] Display bounded HTTP status/detail for failed chat submission, status without untrusted body for model discovery, and safe_message/error_code for a failed accepted run; distinguish cancellation.
- [ ] Update applicable architecture/API docs and changelog, preserve unrelated changes, run targeted/full gates, and smoke the changed chat/error path locally.
- [ ] Build and publish immutable images for the reviewed dev revision; if approved Kolla access exists, deploy and check authenticated chat and failure presentation plus post-rollout canary. Otherwise record the exact access prerequisite.
