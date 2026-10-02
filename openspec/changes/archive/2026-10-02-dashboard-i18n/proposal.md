## Why

The dashboard UI is hard-coded in Korean, so English, Japanese and Chinese speaking researchers cannot use it, and there is no structure through which native speakers can review or improve translations. The product owner works in Korean, so translations must map onto the existing Korean copy rather than replace it.

## What Changes

- Add a dependency-free i18n runtime in `frontend/src/lib/i18n/`: Korean source catalogs and English, Japanese and Simplified Chinese (`zh-CN`) catalogs keyed identically per feature namespace, an ICU MessageFormat subset (arguments, plural, select), safe rich-text segments, locale-aware `Intl` formatting and a fallback chain (ja/zh-CN → en → ko).
- Keep Korean as the default and the byte-identical source UI. The choice persists in the `afterglow_locale` cookie, so SSR, `<html lang>` and hydration render the chosen language; switching re-renders the console chrome in place and remounts only page content.
- Add a language picker (native language names) to the console header, the login page and the landing page.
- Move every user-visible string in public, user, admin and shared frontend surfaces (text, `aria-label`, `title`, placeholders, toasts, confirmations, tutorial tours) into the catalogs. Server-provided text (API errors, OpenStack/Lumen messages, announcements) and tutorial fixture data that imitate backend payloads stay as received.
- Give translators a workflow: `npm --prefix frontend run i18n:check|i18n:scan|i18n:report|i18n:export|i18n:import|i18n:review|i18n:format`, a review manifest that marks each translation as draft, reviewed or outdated against the Korean source hash, CSV round-trip for spreadsheet reviewers, a terminology glossary and Korean/English contribution guides.
- Guard regressions in the frontend unit suite: catalog structure/placeholder/tag/Hangul validation and a hard-coded Korean text scanner with an explicit allowlist.
- Use language-specific CJK font fallbacks so Japanese and Chinese never render Han characters with Korean glyph forms.

## Capabilities

### New Capabilities

- `dashboard-localization`: Korean, English, Japanese and Simplified Chinese console UI with persisted per-browser choice and SSR-consistent rendering.
- `translation-contribution`: catalog validation, review status, CSV exchange and contributor documentation for native-speaker localization.

### Modified Capabilities

- `console-shell`: header gains the language picker; navigation, breadcrumbs, status labels and shared UI primitives read localized messages.

## Impact

Frontend only. Backend APIs, authentication, persisted data and deployment configuration are unchanged; no new runtime dependency. Every existing Korean string is preserved verbatim in `messages/ko`. Machine-drafted en/ja/zh-CN translations ship marked as draft until native reviewers approve them. The separate main checkout has unrelated uncommitted UI work that will need rebasing onto this branch; the hard-coded text scanner identifies any untranslated strings it introduces.
