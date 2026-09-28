# Agent Workflow Specification

## Purpose

Keep the short `AGENTS.md`/`CLAUDE.md` entrypoint actionable while retaining Afterglow's development, design, verification, and architecture contracts. Current source and `ARCHITECTURE.md` take precedence over plans and dated claims.

## Requirements

### Requirement: Work stays on the development branch and has an explicit plan
Before implementation an agent SHALL confirm it is in the `dev` worktree, preserve staged and unstaged user changes, and establish the goal, scope, design, constraints and completion checks. `main` changes and `dev → main` merging belong to the maintainer. The agent SHALL record a new change with `openspec new change <slug> --schema rapid`, fill in its `proposal.md` and `tasks.md`, and update checkboxes while implementing. It SHALL NOT commit, push or archive without explicit authorization for those actions. If authorized to commit, use `feat`, `fix`, `refactor`, `docs`, `test` or `chore` prefix, inspect staged files, and never include `.env` or secrets.

#### Scenario: Worktree contains another user's edits
- **WHEN** a task starts on `dev` with unrelated modifications
- **THEN** the agent plans around those modifications instead of resetting, staging or deleting them, and tracks only the requested change

### Requirement: Architecture evidence matches current source
The agent SHALL read root `ARCHITECTURE.md` before working. For code, config, schema, dependencies, deployment or tests it SHALL update affected architecture sections and detailed `docs/` in the same change; for no-structure-impact fixes it SHALL record why in the latest review summary. After inspecting source, it SHALL run `python3 scripts/check_architecture.py --stamp --summary "<actual review>"` and before submission run `python3 scripts/check_architecture.py --staged` for the intended index. The stamp does not auto-stage. Implemented code, a defined test, a passed local test and live OpenStack observation SHALL be reported separately.

#### Scenario: A source change has no structural impact
- **WHEN** a tested refactor changes implementation but no architecture boundaries
- **THEN** the review summary explains the no-impact decision and the source snapshot is stamped after source review, not in advance

### Requirement: Verification escalates from changed path to full gate
Backend endpoint work SHALL include consumer-relevant pytest coverage under `backend/tests/`. The agent SHALL choose selectors from `npm run test:list`, run exact selectors before named targets (`npm run test:target -- <target>`), then cross-cutting verification as appropriate. Unit (`npm run test:unit`), consumer contract (`npm run test:contract`), isolated functional (`npm run test:functional`) and opt-in live OpenStack (`npm run test:live`) are distinct evidence. Unit tests SHALL remain isolated from external network and credentials; a missing live prerequisite SHALL be reported as a gap, not a pass. If a commit is authorized, `npm run test:gate` (`test:all` plus `lint:backend`) SHALL pass before staging/committing/pushing.

#### Scenario: No live credentials are available
- **WHEN** focused unit and contract tests pass but live OpenStack is inaccessible
- **THEN** the report lists executed checks and explicitly leaves the live verification unclaimed

### Requirement: UI changes follow canonical design rules
Before visual work the agent SHALL read `DESIGN.md` including responsive hierarchy. The precedence is `frontend/src/routes/layout.css` → `frontend/src/lib/design/tokens.ts` → shared UI primitives → feature composition. New colors, states, motion or primitives SHALL be defined in the canonical layer before use, with tests and DESIGN.md updates; new frontend files SHALL NOT add raw hex or palette colors. The agent SHALL verify navigation, table/card fallback, overlays and actions at mobile (<768 px), tablet (768–1023 px) and desktop (>=1024 px), respecting reduced motion.

#### Scenario: A new status treatment is needed
- **WHEN** a feature requires a new status tone
- **THEN** it is introduced in tokens/primitives and verified at the three layout ranges before feature-specific composition

### Requirement: Layer work uses its existing contract
For Palimpsest or Union layer work the agent SHALL read `docs/palimpsest.md`, `docs/squashfs-layer-pipeline.md`, then `union.md`. A layer's digest is the SHA-256 of its `.sqsh` blob bytes; a rebuild produces a new digest and SHALL NOT overwrite a prior immutable layer.

#### Scenario: Layer input changes
- **WHEN** a previous build digest already exists and its input changes
- **THEN** a new content-addressed layer is created rather than replacing the old blob
