## Implementation Tasks

- [x] Add canonical public model/provider projection to Lumen model and catalog responses while preserving internal route keys and display-name overrides.
- [x] Canonicalize Perplexity discovery, create/update encoding, locking, validation, and duplicate detection without rewriting existing rows.
- [x] Route Perplexity Agent, Router, and legacy Sonar API-key calls through explicit safe LiteLLM transports.
- [x] Add ambiguity-safe provider-aware OpenAI and Anthropic compatibility resolution, canonical response IDs, and provider-aware model listing.
- [x] Update Afterglow model administration, model picker, search, clipboard actions, and responsive metadata display to use public IDs.
- [x] Update Afterglow OpenAI and Anthropic SDK examples to send the optional top-level `provider` request field.
- [x] Add and pass focused Lumen regression tests for routing, transport, discovery, compatibility, durable snapshots, and protocol behavior.
- [x] Pass focused Afterglow frontend tests, synthetic SDK/compat smoke, and responsive browser verification.
- [x] Update affected Lumen and Afterglow architecture/detail documentation and changelogs, stamp both architecture snapshots, and pass repository gates.
