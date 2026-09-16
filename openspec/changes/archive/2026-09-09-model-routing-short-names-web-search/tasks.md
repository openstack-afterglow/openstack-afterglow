## Implementation Tasks

- [x] Normalize Lumen `api_model_name` and `display_name` to strip redundant duplicate provider prefixes.
- [x] Update `resolve_api_model` so unique models route without an explicit `provider` parameter while preserving ambiguity guards.
- [x] Detect `web_search` model capability and automatically activate `web_search` tool in Perplexity Agent completions.
- [x] Keep provider-native search distinct from managed search and verify native completion using actual /chat/models response without 422 errors.
- [x] Update Afterglow admin model list to display shortened clean names and show web search badges in model picker and admin list.
- [x] Verify Lumen regression tests and Afterglow frontend tests.
- [x] Update architecture documents and pass all repository gates.
