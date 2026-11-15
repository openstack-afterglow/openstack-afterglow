# Change: Hide unavailable tutorial launchers

## Why

Real non-administrator sessions cannot start ordinary tutorial tours, but `TutorialStartButton` currently renders an enabled launcher and invitation bubble. Clicking silently returns from `startTour`.

## What changes

- Render the launcher, invitation, delayed hint, and route-level wrapper only when the viewport supports tutorials and shared reactive `tourAvailability(tour)` allows this tour.
- Recompute visibility when authentication readiness, session, project-switching, or logout state changes.
- Keep the existing start gate and real-administrator policy unchanged.
- Add component regression coverage and document the visibility policy.

## Impact

Frontend-only presentation change. No API, authorization, resource mutation, or deployment changes.
