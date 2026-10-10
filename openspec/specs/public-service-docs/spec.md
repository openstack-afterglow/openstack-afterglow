# Public service documentation

## Purpose

Provide publicly readable, source-backed Korean, English, Japanese and Simplified Chinese service usage instructions and reliable entry points from Afterglow landing and console surfaces without weakening operational authorization.

## Requirements

### Requirement: Project-independent public documentation
The frontend SHALL expose `/docs` and slash-delimited descendants as public reading routes without requiring login, project selection, or authentication recovery. Documentation reading SHALL NOT start identity verification, session refresh, or authenticated announcement polling. A late expired-session response from an earlier protected-console request SHALL NOT redirect the current documentation reader to login. Existing protected routes and backend authorization SHALL remain unchanged.

#### Scenario: Anonymous reader with unavailable API
- **WHEN** an anonymous reader directly opens `/docs` or a registered guide while the API is unavailable
- **THEN** the guide content and documentation navigation are rendered without a login redirect
- **AND** public branding may use its existing fallback without hiding the documentation

#### Scenario: Expired or project-unselected session
- **WHEN** a reader with an expired stored session or no selected project opens a guide
- **THEN** the article remains readable without auth verification, refresh, or a project-selection gate
- **AND** a signed-in reader without a project is offered the existing project-selection console destination

#### Scenario: A protected-console request expires after entering documentation
- **WHEN** a reader navigates from the protected console to `/docs` or a slash-delimited guide before an earlier console request returns HTTP 401
- **THEN** the current documentation remains readable without a login redirect or authentication-recovery gate
- **AND** documentation does not start authenticated announcement polling or session refresh
- **AND** returning to a protected console route retains its normal authentication and project checks

#### Scenario: Similar protected prefix
- **WHEN** an anonymous reader requests `/docs-admin` or `/docsevil`
- **THEN** the path retains the existing protected-route authentication behavior

### Requirement: Missing-document HTTP recovery
An unregistered guide SHALL return HTTP 404 for anonymous and authenticated navigation, with a documentation-specific recovery link. The authenticated SPA fallback SHALL NOT replace a documentation 404 with HTTP 200.

#### Scenario: Unknown service guide
- **WHEN** an anonymous or authenticated reader requests an unknown `/docs/<slug>`
- **THEN** the response status is 404
- **AND** the page explains that the document is missing and links to the documentation home

### Requirement: Source-backed service usage guides
The documentation SHALL provide Korean, English, Japanese and Simplified Chinese guides for getting started, Nova, Neutron, Octavia, Cinder, Manila, Glance, Object Storage, Trove, Barbican, Drover, Waygate, Lumen, Palimpsest, and external AI MCP connections. Each guide SHALL describe prerequisites, supported usage, result verification, safe cleanup, and troubleshooting using the current console and API contracts. Static guide content SHALL be rendered as escaped text without a new documentation runtime, backend endpoint, or database.

#### Scenario: Resource workflow boundaries
- **WHEN** a reader follows a service guide
- **THEN** the guide distinguishes request acceptance or provisioning status from guest, data-plane, or application readiness
- **AND** unsupported UI actions are identified as external API or CLI procedures rather than advertised as console capabilities
- **AND** cleanup instructions distinguish managed resources, preserved data, and independently created resources

#### Scenario: Service availability and permission boundaries
- **WHEN** a service is disabled or the reader lacks operational permissions
- **THEN** its guide remains readable
- **AND** optional-service footer actions are disabled according to public site-config service settings
- **AND** beta-menu conditions and backend service gates are explained independently where they differ
- **AND** the presence of documentation is not presented as proof of service deployment or successful live operations

### Requirement: Shared documentation entry points
The landing navigation, hero and footer, console header, global navigation drawer, and command palette SHALL provide a Docs destination independent of optional-service visibility. Adding Docs SHALL preserve access to existing console controls without overlap at supported responsive widths.

#### Scenario: Landing and console navigation
- **WHEN** a reader selects Docs from the landing or console navigation
- **THEN** `/docs` is opened with the public documentation shell
- **AND** the shell provides branding, theme control, service navigation and the appropriate existing console destination

#### Scenario: Desktop search density handoff
- **WHEN** the console displays Docs, Cloud Shell and mode switching together
- **THEN** the existing compact search trigger remains available through 1279px
- **AND** the centered expanded trigger is available from 1280px
- **AND** exactly one header search trigger is visible from 768px with no context/search/utility overlap

#### Scenario: Tutorial round trip
- **WHEN** a tutorial reader opens Docs and returns to the console
- **THEN** documentation is not forced back to a tutorial dashboard while being read
- **AND** the existing tab-scoped tutorial profile is preserved on console return and subsequent Docs navigation

### Requirement: Searchable documentation catalogue
The documentation hub SHALL group guides by their existing documentation categories and search service names, summaries, keywords, prerequisites, body text, command examples, and visible link labels and descriptions. Queries SHALL normalize Unicode to NFC, ignore case and whitespace separators, and require every query term to match a guide.

#### Scenario: Body and command discovery
- **WHEN** a reader searches with mixed case, decomposed Korean characters or multiple whitespace-separated terms
- **THEN** all normalized terms must occur in the guide's indexed content
- **AND** command and reference-link descriptions are discoverable without being guide titles

#### Scenario: Empty result recovery
- **WHEN** no guide matches the query
- **THEN** an explicit empty state and reset action are shown
- **AND** resetting restores the complete guide catalogue

### Requirement: Responsive guide and section navigation
Every guide SHALL expose stable section anchors, a matching table of contents, and relevant guide links. Reading SHALL remain contained at supported 320–1440px widths in light and dark themes. Code overflow SHALL be local to the code region rather than causing page overflow.

#### Scenario: Mobile reading and navigation
- **WHEN** a reader uses a viewport below 768px
- **THEN** a disclosure provides service navigation and closes after guide navigation
- **AND** an inline disclosure provides the article table of contents below 1024px
- **AND** selecting a section lands below the sticky header

#### Scenario: Wider reading layout
- **WHEN** a reader uses a viewport from 768px
- **THEN** a service-document sidebar is shown
- **AND** from 1024px the article's table of contents is shown as a separate column
- **AND** guide headings, body, controls and code do not create horizontal page overflow

#### Scenario: Keyboard reading
- **WHEN** a keyboard reader activates the skip link or focuses a horizontally overflowing code region
- **THEN** the skip link transfers focus to the main content
- **AND** the code region supports native keyboard scrolling

### Requirement: Explicit non-executing command copy
A command copy action SHALL copy the exact published command text without executing it. Clipboard failure SHALL provide a visible manual-copy recovery message while keeping the example selectable. Copy feedback SHALL NOT leak from one guide to a different command.

#### Scenario: Clipboard success
- **WHEN** the Clipboard API permits a command copy
- **THEN** the clipboard contains the exact example text including line breaks
- **AND** a success status is displayed without invoking cloud or provider operations

#### Scenario: Clipboard denial and guide change
- **WHEN** command copying is denied or unavailable
- **THEN** a visible message explains how to select and copy the command manually
- **AND** changing guides clears prior command feedback

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

