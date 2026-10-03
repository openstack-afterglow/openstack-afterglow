# Safe SVG Mermaid labels

## Why

Actual compiled chat in the 1.30.0 baseline and dependency-patched frontend renders flowchart nodes with no readable labels. Mermaid's default HTML labels live in foreignObject, which the existing SVG-only sanitizer intentionally removes. Chromium observed two nodes, zero nodeLabel text and no foreignObject in the final DOM.

## What Changes

Set Mermaid's supported root htmlLabels=false option. Keep securityLevel=strict, DOMPurify SVG-only profiles, foreignObject denial and event-handler denial unchanged. This selects native SVG text instead of allowing embedded HTML. No API, provider, model, styling, theme, navigation or motion policy change.

## Acceptance

Rebuild and run canonical frontend images on linux/arm64 and linux/amd64. Real compiled chat must retain the exact flowchart node labels, SVG text, Markdown table, code and KaTeX output while rejecting script/event-handler/javascript-URL content. Verify mobile/tablet/desktop, then existing focused and full gates/typecheck/build. The existing jsdom renderer-failure test remains useful; configuration-copy/mock assertions do not prove actual labels. Browser smoke is the regression evidence because jsdom lacks SVG layout. Archive only this completed change; the ecosystem rollout remains blocked on owner and production prerequisites.
