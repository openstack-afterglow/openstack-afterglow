## Why
Users could not understand the landing page service sections from ASCII character art alone.

## What Changes
- `LandingMotionGraphic` renders simple icon-and-label flow diagrams (inputs → arrow → framed result) using the existing localized `landing.story.diagram.*` labels.
- Motion reuses the `LandingScene` lifecycle (play once when visible, pause offscreen, settle static, replay, reduced-motion static): stages arrive in order, links draw, a light travels each link three times.
- Narrow containers stack the flow vertically.
