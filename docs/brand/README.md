# LineageLens brand assets

The mark is a hollow **source node** joined by a single orthogonal path to a solid
**impact node**: a column traced to what depends on it. The path also reads as an "L".
It is drawn on a 32 × 32 grid with a 3 px line, so it stays legible at 16 px
(`favicon-16.svg` is a pixel-hinted variant for the smallest size).

The wordmark is Inter SemiBold (SIL Open Font License 1.1) converted to outlines, so
the SVGs need no font files.

## Colours

| Role | Hex |
|---|---|
| Accent ("trace blue") | `#1E66F5` |
| Ink | `#18181B` |
| Paper | `#FFFFFF` |
| Dark background | `#0E0E10` |

## Files

| File | Use |
|---|---|
| `mark.svg` | Full-colour mark (app icon, avatars) |
| `mark-mono-black.svg`, `mark-mono-white.svg` | One-colour mark for light / dark backgrounds |
| `glyph.svg` | Mark without the tile, `currentColor` (inline use) |
| `glyph-blue.svg` | Mark without the tile, accent colour |
| `logo-light.svg`, `logo-dark.svg` | Mark + wordmark for light / dark backgrounds |
| `logo-mono-black.svg`, `logo-mono-white.svg` | One-colour logo |
| `logo-light@2x.png`, `logo-dark@2x.png` | Raster logo |
| `favicon.svg`, `favicon-16.svg`, `favicon.ico` (16/32/48) | Browser icons |
| `favicon-16.png`, `favicon-32.png`, `favicon-48.png`, `favicon-192.png`, `favicon-512.png`, `apple-touch-icon.png` (180) | Raster icons |
| `social-preview.png` (+ `-dark`) | GitHub social preview, 1280 × 640 (*Settings → General → Social preview*) |

## Usage

- Keep clear space of at least a quarter of the mark's height around it.
- Do not recolour the mark outside the palette, add effects (gradients, shadows,
  glows) or change the proportions.
- On busy or coloured backgrounds use a monochrome version.

## Regenerating

```bash
pip install fonttools brotli
python tools/brand/build_brand.py      # writes the SVGs in this folder
```

The PNG and ICO files are rendered from these SVGs with headless Chrome and Pillow.
