## Context
Native domains Accounts (3b24b0e94b1d46c9941d515b8c2d397b) and Personal (4661cc1ff17044bfa43f87ded1d8d53f) were created by the operator. UUIDs are deployment facts, not portable source defaults.

## Decisions
Resolve globally unique native names exactly, not display labels. Complete inventory and exact enabled readback are required; case-insensitive collisions fail closed. Unmarked operator domains are allowed only for these reserved native names; explicit conflicting kind is rejected. No domain mutation or creation occurs during enrollment. Historical journal settlement retains original names/markers. Existing accounts and grants are not moved. No config, migration, mapper, or web organization naming changes.

## Risks
Renaming/deleting reserved domains blocks new enrollment. A cloud administrator controls native naming; this trust is explicit. Source is not a production rollout. Existing old writer must be drained before cutover.
