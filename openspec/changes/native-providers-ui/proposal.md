# Native provider catalog and Decision Studio

## Why

Administrators need a source-tracked official model catalog and explicit manual pricing for compatible APIs. Users need a scoped Decisions workspace without mixing structured answers into chat history.

## Changes

- Replace models.dev browser import routes with a read-only native catalog, provenance badges and explicit native-only clearing of stored price overrides.
- Limit native provider creation to OpenAI, Anthropic, Gemini and Perplexity; retain subscription authentication and expose custom OpenAI/Anthropic-compatible endpoints separately.
- Add the decisions endpoint capability, scoped model picker, bounded shared inputs, predicate/choice/score questions and structured answers with usage and cost.
- Add authenticated BFF routing, nine-locale copy, synthetic tutorial fixtures and focused contract/component verification.

## Boundaries

Lumen owns catalog data, routing, authorization, pricing, quotas and provider execution. Afterglow owns presentation and the authenticated browser proxy. No production changes, deployment, paid API requests or architecture stamps belong to this change. Local synthetic evidence does not establish provider or production acceptance.
