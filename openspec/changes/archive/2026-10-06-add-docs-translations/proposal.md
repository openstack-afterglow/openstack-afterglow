# Multilingual public service documentation

## Why

Public `/docs` currently has 14 Korean-only service guides. Readers need English, Japanese and Simplified Chinese documentation with the same actionable content and safety boundaries.

## What changes

- Keep existing Korean `/docs` and `/docs/<slug>` URLs. Add explicit, shareable `?lang=en`, `?lang=ja`, and `?lang=zh-CN` variants; `ko` remains the default. No automatic language redirect or account preference is added.
- Translate every reader-facing field in all 14 guides and the docs shell/index/article/copy/error UI. Keep slugs, section anchors, links, service gates, related guides and executable command syntax canonical. Shared examples use neutral English placeholders/required-variable diagnostics rather than Korean-only code strings; the same final code bytes are used in every locale.
- Provide an always-reachable native language menu. Switching keeps the current article, fragment and existing query parameters; docs navigation keeps the selected language and tutorial context.
- Search the selected language's names, keywords and full content. Load translation dictionaries on demand and cache static catalogs; do not add a runtime i18n service, API, DB or dependency.
- Render correct language in initial SSR and client navigation; restore Korean when returning to the untranslated console. Preserve exact public/auth/404 and project-independent boundaries.
- Require complete dictionaries rather than falling back silently to Korean prose. Japanese/Chinese content wraps using normal CJK line breaking and existing font fallback/token roles.

## Scope and constraints

Only public docs are localized; landing and operational console remain Korean. Chinese means Simplified Chinese (`zh-CN`). Source UI labels may retain Korean in parentheses where needed to identify existing controls. No operational cloud actions, paid inference, secret changes, dependency changes, commit/push/deployment or shared-index mutation. Existing concurrent work stays intact.

## Acceptance

Every language has all 14 guides / 99 sections with translated prose, UI and search; URLs/anchors/commands/gates remain canonical. Real Chromium proves locale navigation, initial SSR/hydration, localized body/keyword search, related/sidebar/index links, copy success/failure/reset, public 404 and mobile/desktop containment. Focused regressions, frontend check/build, scoped architecture guard and OpenSpec validation pass or report exact gaps.
