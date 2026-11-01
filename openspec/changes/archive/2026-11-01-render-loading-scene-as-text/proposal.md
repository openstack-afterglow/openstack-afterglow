## Why
The user clarifies that graphics themselves must be made of text, not drawn shapes with a CRT effect layered over them.
## What Changes
Replace the geometric renderer with a character-cell renderer. Analytic brightness fields select glyphs/colors for the ring, glow, reflection, edge-to-edge water and ambient texture. Vertical system-term rain shares the same grid. No strokes, paths, gradients, image copies or raster glyph substitutes; only text drawing over a flat background. Keep Afterglow palette and motion lifecycle.
