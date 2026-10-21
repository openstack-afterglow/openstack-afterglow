# Resize modal horizontal overflow

## Goal
Remove horizontal scrolling and clipped panel edges from the shared user/admin instance resize dialog.

Also repair the reported current-flavor verification failure in the backend. Trace native metadata and preserve ownership, quota, same-flavor and disk-shrink safeguards; do not suppress the error or guess missing identity.
## Scope and decision
Inspect ResizeModal and Modal sizing. Reuse the established viewport-bounded panel sizing, remove redundant caller margins, and keep long flavor choices within the control width. Do not hide overflow to mask content loss or change resize authority, eligibility, requests, or SHUTOFF restrictions.

## Acceptance
Actual Chromium rendering shows the complete panel, fields and actions without horizontal overflow at mobile, tablet and desktop widths, including long flavor names and error text. Existing resize interaction tests remain passing. Document local verification and archive this rapid change. No deployment.
