# Landing slop cleanup

## Why
The Impeccable overlay flagged the public landing page for a tracked eyebrow above the hero heading, wide letter spacing on the footer tagline, a glowing shadow on link pulses, and overlong centered description lines. The static detector also reported border-built arrowheads as a side-tab accent.

## What changes
- Remove the hero eyebrow element and its `landing.story.hero.eyebrow` message in all locales.
- Set the footer tagline tracking to normal; keep tracked caps labels.
- Remove the pulse glow; draw link arrowheads with `clip-path`, including the vertical layout and forced-colors mode.
- Cap centered feature descriptions at the shared 34rem measure.

## Non-goals
No copy, routing, auth, API or illustration-structure changes. Nested-card advisories in the illustrations are left unchanged.
