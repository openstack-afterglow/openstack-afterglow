## Why
The status strip should rotate characters, and statuses should use the theme static marks.

## What Changes
- Spinner frames `[ | ] [ / ] [ - ] [ \ ]` become the compact LoadingState default; frozen frame `[ | ]` never matches a settled mark.
- `settledSignal` provides `[ + ] [ ! ] [ / ] [ - ] [ · ]`.
- StatusChip replaces its dot: transitions rotate, success/danger tones map to `[ + ]`/`[ ! ]`, explicit `statusColors` signal (canceled) to `[ - ]`, everything else `[ · ]`.
- Theme motion catalog regenerated.
