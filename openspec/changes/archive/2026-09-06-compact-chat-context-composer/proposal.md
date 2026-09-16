# Compact chat context controls

## Why

The context meter and compaction action occupy a separate, visually dominant row above the composer. Context state and existing chat actions should remain reachable without competing with the message workspace.

## What Changes

Move context usage into a small, accessible composer meter beside model controls. Replace the large context bar with a slash-command menu that exposes manual compaction and selected existing chat actions. Render automatic or manual compaction as a live activity in the chat window. Preserve all context safety gates and responsive action reachability.
## Acceptance

- The composer shows known context usage as an accessible compact meter without a separate context bar.
- Typing `/` exposes available actions; selecting `/압축` starts only an eligible manual compaction.
- Slash actions preserve existing chat, temporary-chat, and usage-settings behavior.
- Mobile, tablet, and desktop retain readable context state and usable command actions.
- Automatic and manual compaction appear as a live chat-window activity until terminal state.
