# Place chat command menu above the composer

## Why

Slash suggestions currently render as a passive list without keyboard selection. Commands should behave like a compact palette immediately above the input, support arrow navigation and Tab completion, and expose the model/project actions users expect. The model picker also needs a provider-level navigation rail when several providers are available, while `@` should become the extensible quick-add entry point for attachments and available chat features.

## What Changes

Keep the slash suggestion list outside and before the composer input shell. Add active-option keyboard navigation, Tab completion into the textarea, and exact-command Enter execution. Add new-project and model-selection commands wired to existing dialogs. Turn `@` into a quick-add palette for file attachment, tools/skills, and existing agents. When multiple model providers exist, add a provider selector beside the model list with a horizontal mobile fallback. Export `UsageRing` from the UI barrel so its documented primitive contract is complete.

## Acceptance

- Typing `/` shows the command palette immediately above the textarea and toolbar.
- Arrow keys change the active option, Tab writes the selected command into the textarea, and Enter executes an exact command without sending it as chat text.
- Slash commands include new project and model selection while preserving command disabled reasons and existing actions.
- Typing `@` exposes supported attachment/features plus existing agents through an extensible quick-add list.
- Multiple model providers produce a selectable provider rail; one provider keeps the simpler model list.
- Mobile, tablet, and desktop retain a readable bounded palette, provider navigation, and usable composer controls.
- `UsageRing` is exported by `frontend/src/lib/components/ui/index.ts`.
