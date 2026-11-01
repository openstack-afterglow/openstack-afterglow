# Afterglow loading artwork — character graphics

Open `output/afterglow-loading/index.html` directly. The main artwork uses the selected Afterglow warm palette. It is a standalone HTML/CSS/JavaScript deliverable, not connected to application routes, authentication readiness or real resource loading. No dependencies, network calls or external images are required.

## Character rendering

Every visible scene mark is an upright character drawn with Canvas `fillText` over one flat background fill. Analytic intensity fields select character density, brightness and color to form the ring, soft halo, reflection, full-width water and ambient texture. The renderer does not draw circles, paths, gradients, pixel squares, image copies or geometric overlay effects. Punctuation (`.:;+=*#%@`) and letters from a fixed OpenStack/Afterglow terminology list form the contour and surrounding scene.

Vertical service-term streams share the same grid. Column terms change independently, with sparse character substitutions; brightness modulation and reflected interference use the same elapsed-time clock. Pause and reduced-motion preferences stop all scene updates. Hidden tabs stop scheduling frames. The grid is bounded to approximately 200 columns and the backing canvas to 2.4M pixels / DPR 1.5, with a 24fps ceiling. There is no low-end-device performance qualification.

The native HTML title/status/button remain readable and keyboard accessible. `window.afterglowLoading.setStatus(text)` inserts real host status with `textContent`; no fake percentages or automatic navigation are used. Call `window.afterglowLoading.destroy()` before unmounting to cancel frames and remove listeners/observer. For future Svelte adoption, use component lifecycle, application tokens and existing localization/status primitives; do not import standalone global reset/root defaults into app routes.

The separate `themes.html` retains the previous six palette explorations (`afterglow`, `accent`, `violet`, `cyan`, `jade`, `pearl`). Query values are whitelisted with warm Afterglow fallback. Gallery previews use a fixed time and stay paused. Earlier theme screenshots document an earlier rendering style; current `preview-desktop.png`, `preview-mobile.png` and `preview-afterglow.png` represent the selected character-art version.

## Verification — 2026-11-01

- JS syntax and independent source review: passed, no blocking findings.
- Source drawing-operation inspection: only one flat `fillRect` plus `fillText`; no shape/image rendering calls.
- Isolated Chromium: 320×568, 375×667, 768×1024, 1280×720 and 1440×900 had no viewport overflow and visible status/footer. Desktop/mobile character-art screenshots inspected.
- Pause frame remained unchanged; resumed frame changed over a 650ms sample. An initial immediate consecutive-call comparison failed because the quantized character grid need not change between adjacent captures; the bounded sample interval was corrected and passed.
- Safe status text insertion and zero browser console errors verified.
- Native OS preference changes, actual browser 200% zoom, Safari/Firefox and low-end-device frame-time measurement remain unverified.
- No live app integration, commit, push or deployment. The pre-commit repository-wide `test:gate` was not run for this standalone output.

The ZIP includes `index.html`, `loading.css`, `loading.js`, `themes.html`, `themes.css` and this README.

## Character loading variants — 2026-11-01

Open `output/afterglow-loading/progress.html` for four standalone component studies, styled by `progress.css` and controlled by `progress.js`:

1. A character orbit and determinate progress view with a manually controlled 0–100% slider and illustrative task stages.
2. An indeterminate character bar with `role=progressbar` and no `aria-valuenow`.
3. A polite status strip with explicit loading/success/error text, glyphs and manual state controls.
4. A native table retaining column headers while character placeholders load; `aria-busy` and an external status describe loading without announcing decorative placeholder rows. A manual toggle shows clearly labelled sample data. Small viewports scroll within the table region, not the page.

The page explicitly labels example data and never advances a fake percentage on a timer. `window.afterglowProgress` exposes `setProgress(value)`, `setStatus('loading'|'success'|'error')`, `setTableLoaded(boolean)` and `destroy()`. The stage labels are illustrative workspace-preparation content derived from the demo endpoints, not observed backend stages. A real application adapter must supply its actual stage/error/unknown semantics and existing localized components. This is not an app-ready shared Svelte primitive. Calls after `destroy()`/DOM removal are unsupported. No endpoint, backend or real loading state is changed.

Reduced-motion pauses character animation initially and on preference updates; a user may explicitly resume. Hidden tabs stop the interval and cleanup removes listeners/timer. The native slider and manual buttons remain accessible while motion is paused. The character orbit uses only text content; borders and native controls belong to the comparison-page UI.

Browser verification passed at320/768/1440px without page overflow; known progress clamps at0/100, unknown bar omits numeric progress, error status updates, table busy/data transition and footer hiding work, reset restores samples, and pause/resume freezes/restarts character animation. No console errors. Desktop/mobile screenshots inspected. Independent source review approved after changing the progress heading to a neutral title. Native preference changes, actual200%browser zoom, cross-browser and application integration remain unverified. No full repository pre-commit gate, commit or deployment was requested.

Source ZIP now additionally includes `progress.html`, `progress.css` and `progress.js`.
