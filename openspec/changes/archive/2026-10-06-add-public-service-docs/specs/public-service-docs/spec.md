## ADDED Requirements

### Requirement: Project-independent public documentation
The frontend SHALL expose `/docs` and slash-delimited descendants as public reading routes without requiring login, project selection, or authentication recovery. Documentation reading SHALL NOT start identity verification or session refresh. Existing protected routes and backend authorization SHALL remain unchanged.

#### Scenario: Anonymous reader with unavailable API
- **WHEN** an anonymous reader directly opens `/docs` or a registered guide while the API is unavailable
- **THEN** the guide content and documentation navigation are rendered without a login redirect
- **AND** public branding may use its existing fallback without hiding the documentation

#### Scenario: Expired or project-unselected session
- **WHEN** a reader with an expired stored session or no selected project opens a guide
- **THEN** the article remains readable without auth verification, refresh, or a project-selection gate
- **AND** a signed-in reader without a project is offered the existing project-selection console destination

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
The documentation SHALL provide Korean guides for getting started, Nova, Neutron, Octavia, Cinder, Manila, Glance, Object Storage, Trove, Barbican, Drover, Waygate, Lumen, and Palimpsest. Each guide SHALL describe prerequisites, supported usage, result verification, safe cleanup, and troubleshooting using the current console and API contracts. Static guide content SHALL be rendered as escaped text without a new documentation runtime, backend endpoint, or database.

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
