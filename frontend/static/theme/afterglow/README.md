# Afterglow universal character theme

These portable assets are generated from `frontend/src/lib/design/characterAssets.json` by `python3 scripts/generate-character-assets.py`. Do not hand-edit exported TXT/SVG/catalog/manifest files. `--check` reports missing, changed or obsolete generated assets without writing.

Open `index.html` directly to browse/filter the full catalogue in light/dark appearances. It works from disk without fetching JSON or using a server. All artwork is text-only, static and decorative. No simulated work, percentages, provider calls or media capture occur.

## Files

- `<id>.txt`: exact Unicode character layout; preserve whitespace in a monospace `<pre>` or terminal.
- `<id>.svg`: transparent, text-only SVG using generic monospace; no shapes, paths, embedded images or external fonts. Default warm color is baked as a fallback. Host SVG text font availability may alter appearance; fixed glyph fidelity is not claimed.
- `manifest.json`: version, categories, labels, art and relative file names.
- `index.html`, `catalog.css`, `catalog.js`: standalone review catalogue.

## Integration

In Afterglow use `<AssetGlyph variant="compute" />` and the canonical registry, not raw copies. The existing component supplies theme/font/forced-color behavior; the page owns translated status, headings and recovery actions. Use `LoadingState` and `ProgressTrack` for actual pending or measured progress; `processing`/`progress` files are static illustrations and must never manufacture backend authority or percentages. Treat decorative SVG/TXT as `aria-hidden`, or provide a localized accessible name when the image conveys meaning. Links, controls, real charts, topology, provider branding, uploaded/generated media and operator logos retain their actual semantics/content.

For other frameworks use manifest/TXT with `white-space: pre`, a monospace font, line-height around 1.2–1.35, and host theme colors. SVG loaded through `<img>` is an isolated image: parent CSS variables do not recolor it. For live theme colors use text/inline trusted SVG. No theme persistence or global preference changes are performed by the standalone catalogue.
