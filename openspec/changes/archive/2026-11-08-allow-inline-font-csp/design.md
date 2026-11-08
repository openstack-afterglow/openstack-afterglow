## Context

Afterglow frontend uses SvelteKit server hooks (`frontend/src/hooks.server.ts`) to attach strict HTTP security headers to all responses, including a Content Security Policy (CSP). The `font-src` directive previously allowed only `'self'` and `https://fonts.gstatic.com`. KaTeX (used in chat markdown message rendering) embeds fonts as `data:font/woff2;base64,...` URIs, leading to browser CSP violations.

## Goals / Non-Goals

**Goals:**
- Permit `data:` scheme in `font-src` so KaTeX math fonts render cleanly without browser warnings.
- Keep other CSP directives (`script-src`, `connect-src`, `img-src`, `frame-src`) strictly constrained.
- Maintain full test coverage in `frontend/src/hooks.server.test.ts`.

**Non-Goals:**
- Loosening any other CSP directive (such as `default-src` or `script-src`).
- Re-architecting font delivery or bundling external font packages.

## Decisions

- **Decision:** Add `data:` to `font-src` directly in `buildSecurityHeaders()`.
  - *Rationale:* Fonts cannot execute script code, and `data:` URIs are standard for inlined CSS fonts (like KaTeX).
  - *Alternative Considered:* Extracting KaTeX fonts to static assets. Rejected as unnecessary overhead for standard math glyphs.

## Risks / Trade-offs

- **Risk:** Minor broadening of font sources.
- **Mitigation:** Fonts cannot execute JavaScript. `script-src` remains strictly nonce/hash protected.
