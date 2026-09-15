## Implementation Tasks

- [x] Prove the `--shadow-restraint` defect empirically in the running app rather than by reading CSS.
- [x] Design the radius and elevation token scale and verify it against the densest real surfaces.
- [x] Define the tokens in `layout.css` for dark and `:root.light`, and expose them in `tokens.ts`.
- [x] Reconcile the literal `border-radius` values in `frontend/src/lib/components/ui/*.svelte`.
- [x] Add `designSystemRules` assertions for the new radius and elevation tokens.
- [x] Update the `DESIGN.md` geometry and elevation prose to the shipped names and values.
- [x] Verify visually at mobile, tablet, and desktop, and confirm the overlay layer renders its shadow. Console routes behind authentication were not visually verified; the auth-free `/login` and landing surfaces, plus computed-style probes against the compiled stylesheet, were.
- [x] Run the design target and the frontend unit suite, then re-stamp `ARCHITECTURE.md`.
