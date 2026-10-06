## ADDED Requirements

### Requirement: Complete selectable guide languages
The public documentation SHALL provide Korean, English, Japanese and Simplified Chinese content for every registered guide, including prerequisites, full sections/steps/callouts, command labels, link descriptions and shell/index/article/copy/error UI. It SHALL NOT silently substitute Korean prose for missing translations. Product names and original console labels used to identify real controls MAY remain literal.

#### Scenario: A reader opens any translated guide
- **WHEN** a reader opens `/docs/<slug>?lang=en`, `ja`, or `zh-CN` for a registered guide
- **THEN** initial SSR and hydration provide that language's complete guide and docs controls
- **AND** the document language identifies the chosen language

#### Scenario: Existing URLs remain Korean
- **WHEN** a reader uses an existing docs URL without a supported language selector
- **THEN** documentation remains Korean and does not redirect according to browser or account preferences

### Requirement: Stable locale navigation and operational content
Language switching SHALL preserve the current docs path, fragment and existing query parameters except the language selector. Index/sidebar/breadcrumb/related guide navigation SHALL preserve the selected language and tutorial context. All language variants SHALL use canonical slugs, section IDs, hrefs, service gates, related slugs and executable command bytes.

#### Scenario: Switch an article at a section anchor
- **WHEN** a reader changes language while reading a guide with a fragment and tutorial query
- **THEN** the same guide and section are selected in the new language and tutorial context remains

#### Scenario: Follow a related or sidebar guide
- **WHEN** a reader follows a docs link in a translated guide or index
- **THEN** the destination retains the chosen language and uses canonical guide routes

#### Scenario: Open a language URL with a remembered tutorial session
- **WHEN** a reader with a remembered tutorial profile directly opens a docs URL containing a language, other reader query and section fragment but no tutorial query
- **THEN** tutorial bootstrap/URL repair appends the remembered profile without replacing the language, reader query or fragment
- **AND** disallowed route redirects continue to use the tutorial home rather than carrying their original route context

#### Scenario: Copy after changing language
- **WHEN** a reader copies a translated command block
- **THEN** clipboard bytes equal the canonical executable example and copy feedback is in the selected language
- **AND** prior-language or prior-guide feedback is not retained after navigation

### Requirement: Localized public reading and search
Localized docs SHALL preserve anonymous, expired-session, project-independent and unavailable-API readability, existing protected routes and genuine unknown-guide HTTP 404. Search SHALL operate on the selected language's complete guide content with existing NFC/case-normalized AND semantics. Native language navigation SHALL remain available on mobile/tablet/desktop without page overflow, and Japanese/Chinese prose SHALL support normal CJK line breaking. Returning to the Korean-only console SHALL restore its Korean document language.

#### Scenario: Search native-language terms
- **WHEN** a reader searches an English, Japanese or Chinese body/keyword term and technical token
- **THEN** matching guides are selected from that language's content, with normalized case/whitespace and empty/reset states

#### Scenario: Read translated unknown guide anonymously
- **WHEN** an anonymous reader requests an unregistered docs slug with a supported language
- **THEN** HTTP 404 is preserved and the docs recovery interface uses that language without login redirection

#### Scenario: Narrow translated layout
- **WHEN** a reader uses any supported language at mobile, tablet or desktop widths
- **THEN** language selection, theme, console entry, guide navigation, outline and bounded code scrolling remain reachable and text does not overflow the page

#### Scenario: Return to the operational console
- **WHEN** a reader leaves localized documentation for the existing Korean console or landing
- **THEN** normal authorization behavior and Korean document language are restored
