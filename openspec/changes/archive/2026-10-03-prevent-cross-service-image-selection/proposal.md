## Why

Native serial reproduction showed an unprepared later Waygate target dispatching successfully with Afterglow's saved selection. The first Waygate target was disabled, so it never reset the shared first-target facts. A true readiness flag alone does not identify which service completed selection.

## What Changes

Store the selected service identity with transient first-target facts. Require both readiness and the matching service identity before distributing references or dispatching a published-image consumer. Preserve enabled/source/immutable paths; do not add a fallback or independently resolve on later targets.

## Acceptance

- A prior service's selection cannot authorize a later service whose first target is disabled or in source mode.
- Native failing-before/passing-after regressions cover both cases; existing serial, limit, channel, source, disabled, pin and privilege behavior remains valid.
- Actual native Kolla multiarch rollout smoke passes with the final common task. No application image source changes or production restarts.
- Update architecture/deployment/changelog evidence, run the scoped gate, preserve concurrent work and archive this correction.
