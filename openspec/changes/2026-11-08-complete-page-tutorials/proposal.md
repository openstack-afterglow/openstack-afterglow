# OpenSpec Proposal: complete-page-tutorials

## Why
Only 16 tutorial tours exist, mounted on about 16 pages (instance create, volume, Drover, images, Waygate, several admin
pages). Many other pages have real create or delete flows (file storage, object storage buckets, database instances,
containers, secrets, IAM, chat projects and agents, admin projects, credentials, chat providers and models, quotas,
and more) but only describe them in prose or have no tutorial at all. Users cannot follow a create or delete flow
step by step on those pages.

## What Changes
1. Every route under `frontend/src/routes` that a user can open (dashboard, admin, chat, Lumen, Palimpsest, settings)
   gets a tutorial entry point through `TutorialStartButton`, unless the page has no mutation and is documented as
   read-only (then a short read-only tour, or an explicit "no tutorial" marker recorded in `design.md`).
2. Pages with create or delete flows get step-by-step tours that follow the real UI: open the create or delete control,
   fill the form, submit, observe the result, then cancel or delete the sample resource where the page supports it.
3. Tours are registered in `frontend/src/lib/tutorial/tours.ts` (`TOUR_IDS`, `TOUR_META`, `STEP_BUILDERS`) and mirrored in
   `backend/app/services/tutorial_status.py` `TOUR_IDS`. Each tour's strings exist in all nine locales of
   `frontend/src/lib/i18n/messages/*/tutorial.json`.
4. Tutorial mode (`?tutorial=on`, `?tutorial=admin`) must support every mutation a tour performs. Mock handlers in
   `frontend/src/lib/mockup/` return stateful responses so the step sequence works. Unsupported mutations keep returning
   409 and must not be reached by a tour step.
5. Real-session verification is required before archive: each tour's create and delete path is exercised once against a
   real local session, with resource cleanup.

## Out of Scope
- Changing non-tutorial product behavior, permissions or backend APIs.
- Production deployment or production data changes.
- New mock fidelity beyond what a tour step touches.

## Impact
- Frontend: `lib/tutorial/**`, `lib/mockup/**`, `routes/**` (data-tour anchors), `messages/*/tutorial.json`.
- Backend: `services/tutorial_status.py` TOUR_IDS, tests in `tests/test_tutorial_status*.py`.
- Docs: `ARCHITECTURE.md` (tutorial section), `CHANGELOG.md` `[Unreleased]`, `docs/testing.md`.
