# Reduce dashboard route visual slop

## Goal

Extend the overview refinement on `1b902c1d` to the measured dashboard-route defects without changing identity, permissions, data, copy or mutation contracts. Work only in `ux/slop-pass-2` and its isolated worktree; no integration into dev, publication or deployment.

## Baseline and direction

Use the local tutorial fixtures at 1440×900 and 390×844, CDP detector output, native agent-desktop interaction, screenshots and a recording of the busy instance route. Preserve DESIGN.md's graphite/light surfaces, warm primary action, character assets and existing shared primitives. Layout follows task order: title/actions, summary, search/refresh, inventory, details. Distill redundant containers, preserve information and actions, and polish readable text and semantic headings.

Observed defects: tutorial invitations cover the instance/network refresh label; usage compact cards nest inside their section; project rows, ownership section, alerts and member table repeat bordered surfaces; project headings skip h2; the active-project badge's compounded warm washes fail contrast; Drover's introduction leaves a one-word final line. The canonical network route also nests its Floating IP rows.

`/dashboard/networks` is a 404, not the network list. Its detector finding targets decorative, aria-hidden character art and is not a cramped control. Preserve that artwork and qualify the finding. Audit `/dashboard/network/networks` as the actual network inventory. IAM may redirect under tutorial authority; record the effective route rather than claiming hidden IAM acceptance.

## Changes

Reuse `ResponsiveTable embedded` and `Alert flat`. Flatten ownership and project/Floating IP rows with dividers and neutral selection. Correct project heading levels without changing visual size. Keep tutorial invitation content/actions in normal header flow so they cannot obscure unrelated controls; preserve invitation status and tour startup. Balance whole words in Drover's existing explanation and wrap long cluster status/action rows. No new tokens, gradients, motion, APIs, schema, dependencies or provider behavior.

The paired dark-theme check also exposed usage/activity information using disabled ink-3 and the tutorial-mode banner's warm glow. Reuse ink-2 and neutral restraint elevation rather than changing the palette. A six-width check exposed9px of tablet Drover overflow from a long native status; fix the card's wrapping instead of hiding the status.

## Acceptance

Reconfirm and resolve all real findings on the named and canonical routes at both sizes. Measure changed text colors in both themes. Exercise native search/sort, toggle/disclosure/refresh behavior before and after, preserving destructive-action safety. Record bounded source/local evidence and exceptions, run the canonical gate in a unique detached worktree, update docs/changelog/architecture, archive this change and commit on the requested branch.

## Limits

Tutorial fixtures are synthetic; unsupported project-label and ownership reads remain visible errors. No production resource, authentication or provider acceptance is claimed. No production writes or deployment occur.

The tutorial IAM route redirects to the overview under its existing authority. The redirected overview's dark neutral-chip contrast finding is outside this route pass and is explicitly retained; no IAM authority is fabricated to exercise hidden content. The 404 decorative-art finding is also retained. See `docs/testing.md` and the external proof matrix for exact coverage.
