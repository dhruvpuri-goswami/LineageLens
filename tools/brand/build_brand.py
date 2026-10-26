"""Generate the LineageLens brand SVGs in docs/brand/.

Deterministic and offline. Text is converted to outlined paths from the bundled
Inter variable font (SIL OFL 1.1), so the SVGs render the same everywhere and need
no font files. Requires: fonttools + brotli (only to run this script).

    python tools/brand/build_brand.py

PNG / ICO exports are rendered from these SVGs (see docs/brand/README.md).
"""
from __future__ import annotations

from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "brand"
FONT = ROOT / "frontend" / "node_modules" / "@fontsource-variable" / "inter" / "files" / "inter-latin-wght-normal.woff2"

# Palette. One accent, neutral greys.
BLUE = "#1E66F5"       # accent ("trace blue")
INK = "#18181B"        # near-black
PAPER = "#FFFFFF"
GREY = "#71717A"
LINE = "#D4D4D8"
DARK_BG = "#0E0E10"
DARK_GREY = "#A1A1AA"
DARK_LINE = "#3F3F46"

_fonts: dict[int, TTFont] = {}


def font(weight: int) -> TTFont:
    if weight not in _fonts:
        f = TTFont(str(FONT))
        _fonts[weight] = instancer.instantiateVariableFont(f, {"wght": weight})
    return _fonts[weight]


def text_path(text: str, size: float, x: float, y: float, weight: int = 600, tracking: float = 0.0) -> tuple[str, float]:
    """Return (svg path d, advance width) for text with its baseline at (x, y)."""
    f = font(weight)
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    upm = f["head"].unitsPerEm
    scale = size / upm
    hmtx = f["hmtx"]
    kern = _kerning(f)
    pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    cx = 0.0
    prev = None
    for ch in text:
        g = cmap[ord(ch)]
        if prev is not None:
            cx += kern.get((prev, g), 0)
        tp = TransformPen(pen, (scale, 0, 0, -scale, x + cx * scale, y))
        gs[g].draw(tp)
        cx += hmtx[g][0] + tracking * upm
        prev = g
    return pen.getCommands(), (cx - tracking * upm) * scale


def _kerning(f: TTFont) -> dict:
    """Pair kerning from GPOS PairPos format 1 and 2 (enough for Latin wordmarks)."""
    out: dict = {}
    if "GPOS" not in f:
        return out
    gpos = f["GPOS"].table
    for lookup in gpos.LookupList.Lookup:
        for st in lookup.SubTable:
            if lookup.LookupType == 9:
                st = st.ExtSubTable
            if getattr(st, "LookupType", lookup.LookupType) != 2 and lookup.LookupType not in (2, 9):
                continue
            if not hasattr(st, "Format"):
                continue
            cov = st.Coverage.glyphs
            if st.Format == 1:
                for i, first in enumerate(cov):
                    for pvr in st.PairSet[i].PairValueRecord:
                        v = getattr(pvr.Value1, "XAdvance", 0) if pvr.Value1 else 0
                        if v:
                            out.setdefault((first, pvr.SecondGlyph), v)
            elif st.Format == 2:
                c1 = st.ClassDef1.classDefs
                c2 = st.ClassDef2.classDefs
                for first in cov:
                    k1 = c1.get(first, 0)
                    rec = st.Class1Record[k1]
                    for second, k2 in c2.items():
                        v = getattr(rec.Class2Record[k2].Value1, "XAdvance", 0) if rec.Class2Record[k2].Value1 else 0
                        if v:
                            out.setdefault((first, second), v)
    return out


# --------------------------------------------------------------------------- mark
# 32 x 32 grid. A hollow source node, a single orthogonal path (an "L"), and a
# solid node where the change lands: tracing a column to what depends on it.

def glyph(color: str, s: float = 1.0, ox: float = 0.0, oy: float = 0.0) -> str:
    def p(v: float) -> str:
        return f"{v * s:.3f}".rstrip("0").rstrip(".")
    cx1, cy1, r1, sw1 = 11 + ox, 10.5 + oy, 3.0, 2.5    # source ring
    cx2, cy2, r2 = 21.5 + ox, 21.5 + oy, 3.5             # impact node
    sw = 3.0
    y0 = cy1 + r1 + sw1 / 2                               # line starts at ring edge
    return (
        f'<circle cx="{p(cx1)}" cy="{p(cy1)}" r="{p(r1)}" fill="none" stroke="{color}" stroke-width="{p(sw1)}"/>'
        f'<path d="M{p(cx1)} {p(y0)}V{p(cy2)}H{p(cx2 - r2 + 0.5)}" fill="none" stroke="{color}" stroke-width="{p(sw)}" stroke-linejoin="round"/>'
        f'<circle cx="{p(cx2)}" cy="{p(cy2)}" r="{p(r2)}" fill="{color}"/>'
    )


def tile(fill: str, fg: str, size: float = 32, x: float = 0, y: float = 0) -> str:
    s = size / 32
    return (
        f'<g transform="translate({x} {y})"><rect width="{size:g}" height="{size:g}" rx="{7 * s:g}" fill="{fill}"/>'
        f"{glyph(fg, s)}</g>"
    )


def favicon16() -> str:
    """Pixel-hinted 16 px version: 2 px strokes on whole pixels so it stays crisp."""
    return svg(16, 16, (
        f'<rect width="16" height="16" rx="3.5" fill="{BLUE}"/>'
        f'<circle cx="5" cy="5" r="1.5" fill="none" stroke="{PAPER}" stroke-width="1.6"/>'
        f'<path d="M5 6.8V11H9.5" fill="none" stroke="{PAPER}" stroke-width="2"/>'
        f'<circle cx="11" cy="11" r="2" fill="{PAPER}"/>'
    ), "LineageLens")


def svg(w: float, h: float, body: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}" height="{h:g}" viewBox="0 0 {w:g} {h:g}" role="img" aria-label="{title}">'
        f"<title>{title}</title>{body}</svg>\n"
    )


def lockup(tile_fill: str, tile_fg: str, word: str, bg: str | None = None, pad: float = 0) -> str:
    """Mark + wordmark. 32 px mark, wordmark Inter SemiBold 21 px, optical baseline."""
    size, gap = 32, 10
    d, adv = text_path("LineageLens", 21, pad + size + gap, pad + 23.4, 600, tracking=-0.012)
    w = pad * 2 + size + gap + adv
    h = pad * 2 + size
    body = (f'<rect width="{w:.1f}" height="{h:g}" fill="{bg}"/>' if bg else "")
    body += tile(tile_fill, tile_fg, size, pad, pad) + f'<path d="{d}" fill="{word}"/>'
    return svg(round(w, 1), h, body, "LineageLens")


def social(dark: bool = False) -> str:
    W, H = 1280, 640
    bg, fg, sub, line = (DARK_BG, "#FAFAFA", DARK_GREY, DARK_LINE) if dark else ("#FAFAFA", INK, GREY, LINE)
    card = "#161618" if dark else PAPER
    parts = [f'<rect width="{W}" height="{H}" fill="{bg}"/>']
    # lockup at 2.5x
    x0, y0 = 96, 168
    parts.append(tile(BLUE, PAPER, 80, x0, y0))
    d, _ = text_path("LineageLens", 54, x0 + 80 + 26, y0 + 58.5, 600, tracking=-0.015)
    parts.append(f'<path d="{d}" fill="{fg}"/>')
    d, _ = text_path("Column-level lineage from dbt and Snowflake", 34, x0, 352, 500, tracking=-0.01)
    parts.append(f'<path d="{d}" fill="{fg}"/>')
    d, _ = text_path("to Power BI measures, RLS roles and visuals.", 34, x0, 398, 500, tracking=-0.01)
    parts.append(f'<path d="{d}" fill="{fg}"/>')
    d, _ = text_path("Runs locally  ·  Deterministic parsing  ·  MIT licensed", 22, x0, 470, 400)
    parts.append(f'<path d="{d}" fill="{sub}"/>')
    # a small lineage diagram on the right: four layers, one traced path
    cols = [("dbt", 866), ("Snowflake", 966), ("Model", 1066), ("Visual", 1166)]
    rows = [216, 276, 336, 396]
    nodes = {(0, 1), (0, 2), (1, 0), (1, 2), (2, 1), (2, 2), (2, 3), (3, 0), (3, 2), (3, 3)}
    traced = [(0, 2), (1, 2), (2, 1), (3, 0)]
    edges = [((0, 1), (1, 0)), ((0, 2), (1, 2)), ((1, 2), (2, 2)), ((1, 2), (2, 1)), ((1, 0), (2, 3)),
             ((2, 1), (3, 0)), ((2, 2), (3, 2)), ((2, 3), (3, 3))]
    tset = set(zip(traced, traced[1:]))

    def xy(n):
        return cols[n[0]][1], rows[n[1]]

    def edge(a, b, color, wdt):
        (ax, ay), (bx, by) = xy(a), xy(b)
        mx = (ax + bx) / 2
        return (f'<path d="M{ax} {ay}H{mx}V{by}H{bx}" fill="none" stroke="{color}" stroke-width="{wdt}" '
                f'stroke-linejoin="round"/>')
    for a, b in edges:
        if (a, b) not in tset:
            parts.append(edge(a, b, line, 2))
    for a, b in edges:
        if (a, b) in tset:
            parts.append(edge(a, b, BLUE, 3))
    for n in nodes:
        x, y = xy(n)
        on = n in traced
        if n == traced[0]:
            parts.append(f'<circle cx="{x}" cy="{y}" r="9" fill="{card}" stroke="{BLUE}" stroke-width="3"/>')
        elif on:
            parts.append(f'<circle cx="{x}" cy="{y}" r="{10 if n == traced[-1] else 7}" fill="{BLUE}"/>')
        else:
            parts.append(f'<circle cx="{x}" cy="{y}" r="6" fill="{card}" stroke="{line}" stroke-width="2"/>')
    for label, x in cols:
        d, adv = text_path(label, 15, 0, 0, 500)
        d, _ = text_path(label, 15, x - adv / 2, 456, 500)
        parts.append(f'<path d="{d}" fill="{sub}"/>')
    parts.append(f'<rect x="0" y="{H - 6}" width="{W}" height="6" fill="{BLUE}"/>')
    return svg(W, H, "".join(parts), "LineageLens: column-level lineage from dbt and Snowflake to Power BI")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "mark.svg": svg(32, 32, tile(BLUE, PAPER), "LineageLens"),
        "mark-mono-black.svg": svg(32, 32, tile(INK, PAPER), "LineageLens"),
        "mark-mono-white.svg": svg(32, 32, tile(PAPER, INK), "LineageLens"),
        "glyph.svg": svg(32, 32, glyph("currentColor"), "LineageLens"),
        "glyph-blue.svg": svg(32, 32, glyph(BLUE), "LineageLens"),
        "logo-light.svg": lockup(BLUE, PAPER, INK),
        "logo-dark.svg": lockup(BLUE, PAPER, "#FAFAFA"),
        "logo-mono-black.svg": lockup(INK, PAPER, INK),
        "logo-mono-white.svg": lockup(PAPER, INK, PAPER),
        "favicon.svg": svg(32, 32, tile(BLUE, PAPER), "LineageLens"),
        "favicon-16.svg": favicon16(),
        "social-preview.svg": social(False),
        "social-preview-dark.svg": social(True),
    }
    for name, content in files.items():
        (OUT / name).write_text(content, encoding="utf-8")
        print("wrote", (OUT / name).relative_to(ROOT))


if __name__ == "__main__":
    main()
