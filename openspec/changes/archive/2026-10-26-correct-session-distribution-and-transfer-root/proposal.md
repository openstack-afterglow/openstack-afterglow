## Why
Final review found two source gaps after the prior frozen gate: Helm/Kolla development distribution still sets a one-hour session, and administrator transfer destination exchange uses the caller's project-scoped token instead of the already verified unscoped session root. Clouds disabling scoped-token rescope may reject an otherwise authorized recipient.

## What Changes
Synchronize active default timeout_seconds/timeoutSeconds to86400 in all bundled generation examples; remove the unused absolute_timeout/absoluteTimeout distribution knob, which has no backend consumer. Preserve explicit private overrides. Derive destination credentials solely from require_admin's verified session_token, reject a missing root and retain exact human/project/home/domain proof plus native policy. Re-run final i18n, behavior regressions, real Helm render, installed-SDK synthetic native TCP smoke and the isolated source gate.

## Evidence Boundary
The previous callback14.03s remains unresolved end-to-end. Matched synthetic login controls remove only four directory reads and show no measurable latency improvement. Guard/SDK narrow native-read-only measurements are not whole-route speedups. System:all does not grant a target-project role. No live target-role mutation, private configuration update, shared-service replacement, commit/push or deployment.
