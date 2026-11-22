# UI audit follow-up after 1.32.32

## Why
The 1.32.32 audit left real findings open: decorative eyebrows above headings, text under 11px, 3px colored side stripes, an unused gradient-text component, rainbow summary tiles and docs paragraphs wider than 80 characters. The 1.32.32 CHANGELOG also overstated that VM monitoring cards keep their height while loading.

## What changes
- Remove eyebrows: docs guide header (duplicated breadcrumb), docs home, image repository detail, object-storage browser, Notion global gate; drop their three orphaned i18n keys in all locales.
- Raise text under 11px to 11px: command palette keys, network map, quota form badges, image repository table headers, landing hero footer.
- Replace colored `border-left` stripes with a dot (topology interface rows) or background (monitoring list, folder picker, chat blockquote); delete unused `GradientText`.
- Make decorative `StatTile` accents neutral on chat statistics, subnet usage, activity and bucket summaries; keep semantic rose/emerald.
- Cap docs prose and screenshot captions at 72ch.
- Correct the 1.32.32 CHANGELOG card-height wording. Chat blockquotes use a 1px neutral line (not a fill, which would collide with the code-block fill); the monitoring list uses a separate dot token and a hover class that does not override the selected row.

## Measured
`/docs/lumen` and `/docs/mcp` at 1280px: maximum paragraph measure 72ch (previously up to 102ch from the audit, 80.6ch captions before the final cap); no horizontal overflow at 390px.

## Non-goals
`uppercase tracking-wide` table headers and form labels (about 300 uses) are a project convention, not an eyebrow, and are unchanged. Neutral 2px tree guide lines (EvidenceMap, TaskTree, TopologyNetworkPanel) are unchanged. No API, auth or data change; no version bump.
