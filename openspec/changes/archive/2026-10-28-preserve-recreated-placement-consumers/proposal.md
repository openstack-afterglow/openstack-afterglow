# Preserve recreated Placement consumers

## Why
The domain-pool allocation postcheck and scheduler cleanup treat matching consumer generation/shape/owner as proof that an initially empty consumer still belongs to the failed request. Placement deletes consumer rows with their allocations and recreation restarts generation, so an independent successful replacement can be erased by an old failure handler. Earlier nonempty-preimage ABA acceptance did not cover this initially-empty case.

## What Changes
Do not synthesize an incarnation identity from generation, allocation shape, owner, or a Nova-local lock. The pinned public Placement API has no checked incarnation/serialization proof covering every competing writer. Both extension failure handlers must retain nonempty uncertain allocations, report exact consumer IDs and fail closed for explicit reconciliation. Already empty consumers can be acknowledged as released; explicit native lifecycle release remains native behavior. No new retry, marker inventory, shared-service patch, cross-request auth cache or production mutation.

## Acceptance
- Installed real Placement regressions recreate the same UUID/shape/owner/generation between commit and cleanup for both hook and scheduler paths; both fail before the correction by deleting the replacement.
- After correction, replacement allocations and unrelated consumers survive; errors identify unresolved consumer IDs; failures do not acknowledge admission.
- Existing multicreate/concurrency tests express accepted admissions versus retained uncertain reservations honestly, without weakening native quota denial or overwriting historical receipts.
- Both installed native architectures pass; affected backend regressions/full isolated gate and architecture/spec/operator documents describe the revised boundary.
- Source only: no commit/push/deploy, operational IAM/quota/config/VM/volume or shared datastore changes.
