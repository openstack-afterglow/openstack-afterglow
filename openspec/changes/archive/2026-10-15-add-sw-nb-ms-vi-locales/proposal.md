## Why

Users need Swahili for Tanzania, Norwegian Bokmål, Malay for Malaysia, and Vietnamese throughout the existing multilingual browser interface. A language choice must remain consistent across public documentation, login, and authenticated pages through the shared locale cookie.

## What Changes

- Add `sw` (Kiswahili; Intl `sw-TZ`), `nb` (Norsk bokmål; Intl `nb-NO`), `ms` (Bahasa Melayu; Intl `ms-MY`), and `vi` (Tiếng Việt; Intl `vi-VN`) alongside the existing four locales.
- Provide complete draft translations for every current UI namespace and typed public guide dictionary; preserve variables, rich tags, code, identifiers, links, product names, source meaning, and safety warnings.
- Extend the native language menu, formatting and validation tools, docs loaders/UI dictionaries, contributor glossary and review manifests. Keep Korean default and English-then-Korean fallback for non-English translations.
- Preserve the previously implemented shared-cookie navigation behavior in this latest-dev localization worktree, including explicit docs language selection and safe preloading.
- Exercise all eight locale contracts and actual responsive browser behavior for the four added languages.

## Capabilities

### New Capabilities

- Full browser and public-documentation localization in Swahili, Norwegian Bokmål, Malay, and Vietnamese.

### Modified Capabilities

- Existing locale registration, formatting, catalog validation, and shared language preference accept eight locales.

## Impact

Frontend catalogs, documentation dictionaries, locale menu/runtime/server integration and affected tests/docs only. Work is isolated in `/Users/pieroot/code/afterglow-i18n` on `i18n`, initially fast-forwarded to GitHub dev `08e272422cd855b30d39929c24993047ec0cd6ad`. Preserve the shared dev checkout and other worktrees. No API, authentication authority, database, dependencies, production configuration, deployment, commit, or push is requested. Translation content is machine-authored draft, not native-speaker approval.
