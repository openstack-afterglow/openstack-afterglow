---
title: Frontend localization
lang: en
nav_order: 9
---

# Frontend localization

Afterglow supports Korean (`ko`, source and default), English (`en`), Japanese (`ja`) and Simplified Chinese (`zh-CN`). Each feature namespace maps the same keys in `frontend/src/lib/i18n/messages/<locale>/<namespace>.json`. English is the reference for contributors who do not read Korean. Resource names, user input, API identifiers and product names stay unchanged. Server errors, operator-authored site descriptions and announcements, and tutorial fixtures representing server data remain as received.

[Korean guide](../frontend-localization.md) · [Architecture](../../ARCHITECTURE.md) · [Terminology glossary](../../frontend/src/lib/i18n/glossary.csv)

## How to translate and review with a spreadsheet

Use Node.js 20 or later and a checkout of the repository. Run commands from the repository root. Contributors without a development environment can request a CSV from a maintainer.

```bash
npm --prefix frontend run i18n:report -- --locale ja --by-namespace
npm --prefix frontend run i18n:export -- --locale ja --namespace common --out /tmp/afterglow-ja.csv
```

Exports are UTF-8 with a BOM. Columns are `namespace`, `key`, `source_ko`, `reference_en`, `translation` and `status`. **Edit only `translation`**, preserving headers, keys and Korean source. Save as UTF-8 CSV with quoted commas, quotes and embedded newlines intact. If English is ambiguous, consult the Korean source and the actual screen.

Meaningful leading/trailing whitespace and embedded newlines are preserved. Duplicate headers, inconsistent record widths and unclosed quotes are errors. Unreadable or malformed catalog/review JSON stops writes and review marking; existing files are never replaced with empty data after a load failure.

```bash
npm --prefix frontend run i18n:import -- --locale ja --file /tmp/afterglow-ja.csv
npm --prefix frontend run i18n:check
```

Empty translation cells are skipped, not used to delete existing translations. If any row has stale Korean source, invalid syntax or incompatible arguments/tags, the entire import is rejected. Fix the errors or export a fresh CSV. Use `--reviewed` only after a native speaker has reviewed meaning, terminology and context.

```bash
npm --prefix frontend run i18n:import -- --locale ja --file /tmp/afterglow-ja.csv --reviewed
npm --prefix frontend run i18n:report -- --locale ja
```

For direct JSON edits, mark specific reviewed keys:

```bash
npm --prefix frontend run i18n:review -- --locale ja --namespace common --key actions.cancel
npm --prefix frontend run i18n:format
npm --prefix frontend run i18n:check
```

Include the translation files and `review/<locale>.json` in the same PR. The review command rejects syntax, argument and tag errors in selected translations without partially changing review records. Review marking is a human declaration, not automatic quality certification. Initial English, Japanese and Chinese translations are unreviewed drafts.

## Review states

| State | Meaning |
|---|---|
| `draft` | Translation exists without a review record |
| `reviewed` | Review record matches the current Korean source hash |
| `outdated` | Korean source changed after review |
| `missing` | Translation absent or empty |

Manifests map `namespace:key` to the first 16 hexadecimal characters of the Korean source SHA-256. They do not hash the translation itself: edits to reviewed translations still need human re-review. `i18n:check` checks missing/extra keys, syntax, argument/tag parity, rich tag balance/nesting on ICU render paths and leftover Hangul in non-Korean catalogs. Humans must check meaning and naturalness.

## Message reference

- Keys are descriptive dotted lowerCamelCase: `deleteDialog.body`.
- Preserve all `{name}` placeholders, but reorder them to suit the language.
- English plurals may use `{count, plural, one {# instance} other {# instances}}`. `other` is required and callers must pass a number. Korean, Japanese and Chinese can use `{count}` without plural branching.
- `select` also requires `other`. ICU `number`, `date`, `selectordinal` and `offset` are unsupported.
- Quote literal ICU braces with apostrophes (`'{'name'}'`); use `''` for an apostrophe.
- Preserve source markup such as `<strong>`, `<em>`, `<code>`, `<kbd>`, `<br/>` and custom tags. Do not insert URLs or arbitrary HTML.
- Rich tags must close and nest correctly in every rendered result. Prefer placing a tag around the whole plural or closing it inside each branch. Standalone custom code hints such as `<model>` are not treated as unclosed rich markup.
- Follow the [glossary](../../frontend/src/lib/i18n/glossary.csv). Preserve meaning, detail and warning severity. Keep product names, identifiers and commands unchanged.
- English: concise sentence case. Japanese: polite sentences, noun/action labels, Japanese punctuation. Chinese: Simplified Chinese, full-width punctuation and spaces between Chinese and Latin words/numeric placeholders.

## How to identify a key on screen

Language pickers show each language's native name on the public page, login page and console header. Selection persists in the `afterglow_locale` cookie for one year and determines the next server-rendered HTML language. Browser language is not auto-detected; missing or invalid preferences use Korean.

In the browser developer console:

```js
localStorage.setItem('afterglow.i18n.debug', 'keys');
location.reload();
```

Messages now display as `namespace:key`. To disable:

```js
localStorage.removeItem('afterglow.i18n.debug');
location.reload();
```

Key mode activates after hydration. Switching language remounts page content and can reset unsaved page forms. The header, expanded sidebar sections, VM creation panel and root-mounted Cloud Shell/upload state stay mounted. Existing toasts and stored error messages may keep the language captured when the event occurred. Review line wrapping, clipped buttons and accessible labels at narrow widths as well as desktop.

Dashboard, administrator and Palimpsest layouts remount only ordinary page children inside `main`. Container detail and the Drover list, detail and administrator list are exceptions: they keep the page, live WebSocket and scrollback mounted while updating display text and terminal accessible names. Palimpsest package drafts and one-time issued secrets are still discarded, so store a needed secret securely before changing language. Security-group unions retain policy semantics and ordering while calculating display labels in the active locale. The Korean suffix in image-style guidance is the actual provider prompt, not a missing translation.

## Starting or resuming developer work

Perform localization code changes only in the user-approved, dedicated `i18n` worktree. Every session must fetch the latest GitHub `dev`, merge it and resolve conflicts before translating newly added or changed surfaces. Preserve existing work; do not switch the shared checkout or rebase/force-push the published `i18n` branch.

```bash
git fetch origin dev
git merge origin/dev
git merge-base --is-ancestor origin/dev HEAD
npm --prefix frontend run i18n:check
npm --prefix frontend run i18n:scan
```

The initial post-merge checks identify new omissions and define the work scope. After updating translations, repeat the checks, relevant tests and actual four-locale UI verification. Fetch again before completion/push; if dev advanced, integrate and reverify. Record the incorporated dev SHA in OpenSpec and the completion report. Follow the detailed [agent development guide](../agent-development-guide.md). Spreadsheet contributors receive fresh CSV exports from maintainers working against this synchronized source.

## Developer contract

`ns/<namespace>.ts` types keys from Korean JSON and eager-imports all four catalogs. Catalogs travel with code importing the namespace. Call `t()` from markup, `$derived`, getters or event-time functions, never module scope or SvelteKit `load`. The server locale initializes at the beginning of synchronous root layout rendering; translation outside that render can mix request languages.

```svelte
<script lang="ts">
  import { t } from '$lib/i18n/ns/common';
</script>

<button>{t('actions.cancel')}</button>
```

Use `t.rich(key, values)` and `<RichText segments={...} />` for tagged messages. Interpolated values are protected as text, not HTML. Plain `t()` preserves tag characters and must not render rich messages. Wire interactive links through custom snippets; child element styles require `:global(...)` or the `classes` prop.

Global Cloud Shell, container terminals and the k3s shell use `terminalLocale.ts` to update xterm's input accessible name and excessive-output announcement. Locale updates do not translate or reset existing terminal buffers or remote output. The Korean catalog preserves the English announcements present in the original UI.

Call `intlLocale()` at formatting time for displayed numbers/dates. Do not modify API ISO timestamps, identifiers, code or backend request data. Scan hard-coded Korean text:

```bash
npm --prefix frontend run i18n:scan
```

Intentional server fixture data, parsing regexes or operator configuration belongs in `hardcoded-text-allowlist.json` with an exact line and justification. Do not allow entire files to hide UI omissions. The scanner detects Hangul, not hard-coded English.

## Troubleshooting

- `argument-mismatch`: restore the source placeholder names.
- `tag-mismatch`: preserve the source tag structure; do not add HTML.
- `rich-structure`: check opening/closing tags and nesting in each ICU render path. Keeping the same flat tag counts is not sufficient.
- `syntax`: inspect `other` branches, braces and apostrophe quoting.
- `Korean source changed since export`: re-export and re-review against current source.
- `namespace:key` on screen: either key mode is enabled or the message is missing from every fallback catalog.
- Japanese/Chinese typography differs across machines: Latin text uses bundled faces and CJK uses language-appropriate system fonts. See [DESIGN.md](../../DESIGN.md).
