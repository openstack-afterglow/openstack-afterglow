# Admin model provider tabs and kind filters

## Why
The administrator model registry currently uses model-kind tabs, a separate provider dropdown, and a full native catalog panel. The layout obscures provider-first browsing and duplicates catalog information already available during registration and pricing workflows.

## What changes
- Use AI provider tabs for registered-model browsing.
- Use multi-select model-kind chips within each provider tab.
- Remove the full native catalog panel from the top of model settings; retain catalog-backed discovery and pricing behavior.
- Remove the redundant domain/project history-scope notice from the chat sidebar without changing history ownership or scope.

## Non-goals
- No backend API, persistence, authorization, or chat-history scope changes.
- No removal of the native catalog API or its registration/pricing use.
