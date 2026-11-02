# Afterglow viewport-fit login/logout studies

Open `index.html` to compare login/logout in both orientations, or `login.html` / `logout.html` for live responsive examples. These are standalone designs; actual application routes and authentication/logout logic are not changed.

## Viewport layout

The auth examples use100dvh with fixed header/footer slots and a flexible main area. No body overflow:hidden rule suppresses otherwise inaccessible controls. Borders receive explicit row space to avoid1px scrollbars.

- Large screens retain a side-by-side character-art/form composition.
- Tall tablets use a small horizontal artwork banner above a centered form.
- Small portrait screens reduce artwork and whitespace; shorter screens omit the decorative panel/footer.
- Short landscape screens place the two inputs side by side, with login and SSO below them in the same row. Recovery/help actions remain reachable beneath the status text.
- Logout retains all three cleanup steps, status copy and return-button gating; the artwork yields space before task content does.

`logout.html` provides working/done/server-warning/local-error examples via the header selector. They never run actual logout or clear browser/session data. Successful/local-cleaned examples permit explicit navigation to the local login example; active/local-unconfirmed examples keep the return button disabled. There is no automatic navigation or fake timed progress.

## Validation — 2026-11-02

Tested20 viewport sizes:320×480,480×320,320×568,568×320,360×640,640×360,390×844,844×390,768×1024,1024×768,820×1180,1180×820,1366×768,768×1366,1920×1080,1080×1920,2560×1440,1440×2560,280×653,653×280.

Each size was tested with five login message states (initial, submit notice, SSO notice, recovery notice, guide notice) and four logout states:100+80=180 combinations. Every case had scrollWidth≤viewport width and scrollHeight≤viewport height, and every displayed input/button/select/link remained within the viewport. Initial1px footer-border overflow was found and corrected; the final full matrix had no failures. A light480×320 logout error view also had exact viewport dimensions. Complete/local-error return-button conditions and aria-busy were checked. Browser keyboard and dynamic native mobile chrome were not emulated.

Screenshots cover four device classes in both orientations for both pages (16images), plus a compact landscape error view. Snapshot URLs use `?preview=1` for a paused scene. Normal pages animate unless reduced motion is enabled. Independent source review approved. JavaScript syntax and gallery image loading were verified.

## Preview safety and actual adoption

No login, SSO, recovery, help or logout request is connected. Login inputs have no name attributes, scripts do not read/log/send/persist their values, and submit is prevented. Demo notices explicitly distinguish previews from actual operations. Do not use real credentials for testing.

Actual adoption must preserve existing app error/readiness states, native IME/autofill, CSRF/auth/session behavior, operator logos, SSO/signup visibility and registered localization. Do not import standalone root/reset defaults into app routes. The current proof is isolated Chromium at normal scale and the documented sizes; native software keyboard, browser zoom/text scaling, nine locales and other browsers remain unverified. Do not hide actual security/error content solely to force a fixed viewport under those conditions.

The ZIP includes responsive HTML/CSS/JS, the original Afterglow symbol, comparison gallery and screenshots. The gallery itself is a scrollable catalog; only login/logout pages have the viewport-fit requirement.
