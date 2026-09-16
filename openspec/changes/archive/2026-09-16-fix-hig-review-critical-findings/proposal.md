## Why

A five-lens Apple HIG review across nine surface clusters produced 69 source-verified findings — 27 Critical, 28 High, 14 Medium. The warm-colour defect was fixed separately. This change clears the accessibility and theme defects that remained, all of them measured rather than asserted.

## What Changes

- Complete the semantic `-text` token family. `Alert` painted its title and body in the raw tone over a 12% wash of that same tone, which measures 2.89:1 for success through 4.37:1 for info in light mode — every tone below AA. Dark already cleared 4.96:1, so dark aliases the tone and only `:root.light` carries a darker value. The wash and border keep the raw tone, so tone identity is unchanged.
- Make `Toast` perceivable. The container and every item carried no role and no `aria-live` despite 384 call sites. Errors now interrupt with `role="alert"`; everything else announces politely.
- Connect `Field`'s help and error to their input. `Field` rendered the message with id `${for}-message` and nothing referenced it; the text primitives already accepted `ariaDescribedBy` but no caller passed it. They now default it from the `id` the caller already supplies, so every existing pair associates without touching a call site.
- Give `LoadingSkeleton` a named live region, `Modal` a scroll path for panels taller than the viewport, and both sidebars `aria-expanded` on every group.
- Move placeholders and the shell's section labels, username, empty-state sentence, project descriptions, actionable buttons, record-range readout and meter readout off `--color-ink-3`, which `DESIGN.md` reserves for disabled text and which measures 2.56:1 in light.
- Replace dark-theme palette literals rendering raw on white panels with semantic tokens, and raise the GitLab button's label off 2.60:1 on the brand fill.
- Restore a visible focus indicator on the 12 controls that removed the outline and put nothing back. The warm-colour fix already restored the other 287.
- Make the volume action menu reachable below 1024px, keep filtered landing cards legible, and stop the chat composer's context status from leaving the accessibility tree below 768px.

## Capabilities

### Modified Capabilities

- Alerts, toasts, loading states, form errors and group state are perceivable without sight.
- Light mode no longer paints information in a disabled token or a dark-theme palette value.

## Impact

- `layout.css`, `tokens.ts`, `DESIGN.md`, the design-system tests and 30 component and route files change.
- No fill tone, gradient or brand colour changes value. Only text colours move, and only where they were measured below AA.
- `ARCHITECTURE.md` is re-stamped.
- The review's remaining High and Medium findings are not addressed here.
