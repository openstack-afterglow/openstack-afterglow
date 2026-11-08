## ADDED Requirements

### Requirement: Allow Data URI Fonts in Frontend CSP

The frontend SvelteKit server hooks MUST permit `data:` URIs in the `font-src` Content Security Policy directive to allow inlined CSS fonts (such as KaTeX math glyphs) to load without browser violations.

#### Scenario: KaTeX inlined font load
- **WHEN** a client browser renders a page containing KaTeX inlined font data URIs
- **THEN** the response `Content-Security-Policy` header includes `font-src 'self' data: https://fonts.gstatic.com`
- **AND** the browser does not reject the font with a CSP violation
