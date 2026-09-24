## Context

`ChatApiKeysManager` currently renders four complete connection guides in one card after loading validated Lumen discovery URLs. The result is a long settings surface where users must scan unrelated clients before reaching the one they use. Afterglow already has a keyboard-accessible shared `Tabs` primitive and requires mobile, tablet, and desktop information parity.

## Goals / Non-Goals

**Goals:**

- Make Codex, Claude Code, OpenAI, and Claude guides directly selectable.
- Render only the selected guide while retaining every existing setup detail and copy payload.
- Preserve discovery URL validation, retry behavior, responsive containment, and accessible keyboard navigation.

**Non-Goals:**

- Change Lumen discovery, API-key issuance, quota, provider, authentication, or backend contracts.
- Persist the selected guide across sessions or encode it in the URL.
- Add a second tab implementation or modify the shared Tabs primitive.

## Decisions

1. Reuse `Tabs.svelte` with a local `ClientGuide` union and caller-owned panel. This preserves the established tablist, roving focus, Arrow/Home/End navigation, manual activation, and tab/panel ARIA linkage. Four ad hoc buttons would duplicate behavior and risk an inaccessible selector.
2. Default to `codex`, matching the requested presentation order. The panel changes locally without a request because all four examples derive from the same already-loaded discovery response.
3. Keep each guide's prose next to its own copy action and code block. Shared API-key/model/provider guidance remains concise, while package and file-specific instructions move into the relevant panel so inactive clients do not create visual length.
4. Keep code blocks horizontally scrollable inside the existing card, but never make the client selector itself a scroll container: the shared Tabs `overflow-x: auto` computes vertical overflow as `auto`, and the existing tab button/border geometry creates a one-pixel vertical scrollbar even when every tab fits. Scope a non-scrolling layout to this guide; mobile uses a two-column tab grid at the existing 768px breakpoint, while wider widths wrap if necessary. Leave other Tabs consumers unchanged.
5. Test the observable selector contract: one panel and one snippet at a time, exact discovered URL/config content after switching, copy payload for every client, and discovery failure/retry behavior.

## Risks / Trade-offs

- [Risk] Hidden guides are no longer searchable in the page until selected. → Mitigation: four persistent, plainly named tabs make every client reachable in one action.
- [Risk] A tab label and panel ID can drift apart. → Mitigation: derive both from the same fixed guide item list and assert ARIA linkage through the shared Tabs contract.
- [Risk] Existing tests assume all four code blocks exist simultaneously. → Mitigation: replace that implementation assumption with interaction-level assertions across the four selected panels.

## Migration Plan

Deploy as a frontend-only cutover. No data migration or compatibility shim is required. Rollback restores the previous component and test rendering; API and persisted state are unchanged.

## Open Questions

없음.
