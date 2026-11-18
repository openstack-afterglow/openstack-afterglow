## Why

Owner requests (2026-11-18/19): model pickers do not show or let users choose the provider; chat history and the tool list change when the user switches projects inside the same domain; API keys are bound to one project and there is no domain-owned machine credential; the Lumen client installer asks users to paste service URLs; and chat memory should become the owner's Agent Vault, with the records Agent Vault keeps in SQLite held in the server database.

## What Changes

- **Provider → model selection:** one shared picker for chat, regeneration, agents and the embedding, decision, audio, realtime and image Studios. Same-name models under different providers are distinct choices; requests carry the exact catalog row (`model_row_id`). Requires Lumen 0.6.21.
- **Domain-wide history and tools:** within one Keystone domain the same user sees the same conversations, agents, memory and tool connections in every project. Switching projects inside a domain keeps the views; switching domains resets them. Runs, usage attribution and cloud tools still use the selected project. Connections → Manage lists and restores archived duplicate connections and tools (organization items by verified managers).
- **Keys and billing:** personal keys are user-bound and project-independent; "service keys" are domain-owned machine credentials (like OpenAI service accounts or Anthropic/Gemini service keys) that only current domain managers create and manage, and they keep working when the creator loses the role. Both are model-API only. Usage is billed per domain from a prepaid domain credit pool (system-admin top-ups, manager monthly limit under an admin ceiling); personal keys bill the user. Existing project keys become personal keys.
- **Installer:** Afterglow embeds the configured Lumen external URL into `/install/lumen.sh` and `/install/lumen.ps1` at startup; copy commands no longer take URL arguments, and an unconfigured URL yields a failing script and hidden commands.
- **Vault memory:** the chat settings memory section becomes the Agent Vault UI backed by Lumen's native vault (encrypted notes and records in MariaDB, dashboard sessions only); `memory.md` is rendered from the vault.

## Non-goals

- No OpenStack authority for any API key; no external (API-key) access to the vault.
- No import of the owner's local `~/.vault`.
- No change to cloud-tool targeting: always the selected project.

## Dependencies

- Lumen 0.6.21 (migrations 036–040: domain scope, domain credit pools, key kinds, model identity, vault) must be deployed first, and domain credit pools need opening top-ups before the cutover.
