## Context

The canonical checkout is on dev f8d4395b with unrelated in-flight password-reset edits and two worktree-policy edits. Eight historical worktrees remain; some have uncommitted source, some only post-release evidence, and some implementations were already replaced by later dev changes.

## Goals / Non-Goals

**Goals:** Reconcile every remaining worktree, merge all applicable results into canonical dev, validate the actual integrated source, commit the policy and remove completed work directories safely.

**Non-Goals:** Production/native/schema changes, new version/tag, unrelated feature development, main merges, discarding concurrent user work or weakening modern security/session contracts.

## Decisions

- Build on an isolated dev clone and capture original heads, binary diffs, public untracked files and protected ignored files before destructive operations. Do not stash/reset the shared checkout.
- Compare old deltas, current behavior and Git history. Port only a genuine missing behavior; retain evolved dev behavior when it demonstrably supersedes an older proposal. Record a concrete disposition for each source tree, not merely an archive flag or a dirty status.
- One integration owner controls shared docs, merge commits and final staging. UI/model, localization and legacy security slices own disjoint implementation files and skip mid-flight builds/tests; final verification runs once against the integrated source.
- Preserve archived release evidence as historical evidence, not current production acceptance. Resolve stale documentation snapshots without rolling back newer source or claims.
- Before updating canonical dev, verify that shared source/index have not changed unexpectedly. Carry unrelated local edits unchanged through the final normal merge; explicitly resolve overlaps without dropping or committing unrelated work.
- After validation, preserve branches and protected recovery artifacts while removing completed source directories and the isolated integration clone.

## Risks / Trade-offs

- Old snapshots can undo newer authority or localization behavior: require delta-level evidence and retain modern code when superseded.
- Concurrent edits can race final integration: re-check exact file/index state before applying and retry against a fresh snapshot if it changed.
- A known pre-existing setup PTY cancellation timeout can fail the full gate: report actual output and investigate rather than weaken tests or rerun until green.
