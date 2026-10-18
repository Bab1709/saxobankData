"""A graphical overview of the portfolio as one self-contained HTML file.

Usage:
    python -m saxobank.report           # real data from data/ -> output/report.html
    python -m saxobank.report --demo    # made-up data -> output/report_demo.html

The page has no external scripts, fonts or network calls, so the data never
leaves the computer. Charts are plain SVG drawn here; a few lines of
JavaScript add tooltips on hover and keyboard focus.
"""
from __future__ import annotations

import html
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

MONTHS_DA = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


# --- Formatting ---------------------------------------------------------------

def dk(value: float | None, decimals: int = 0) -> str:
    """Danish number format: 1.234,5"""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".").replace("-", "−")


def kr(value: float | None) -> str:
    return f"{dk(value)} kr"


def pct(value: float | None, decimals: int = 1, sign: bool = False) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    text = dk(value, decimals) + " %"
    return ("+" + text) if sign and value > 0 else text


def compact(value: float) -> str:
    """Axis ticks: 0, 50.000, 1,2 mio."""
    if abs(value) >= 1_000_000:
        return dk(value / 1_000_000, 1).rstrip("0").rstrip(",") + " mio."
    return dk(value)


def day(d: date) -> str:
    return f"{d.day}. {MONTHS_DA[d.month - 1]} {d.year}"


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    if hi == lo:
        hi = lo + 1
    raw = (hi - lo) / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    v = math.floor(lo / step) * step
    ticks = [round(v, 10)]
    while ticks[-1] < hi:
        v += step
        ticks.append(round(v, 10))
    return ticks


def tip(*rows: str) -> str:
    """Tooltip rows, joined for the data-tip attribute. The first row is the
    heading; '::' splits a row into value and label."""
    return esc("|".join(rows))


# --- Charts -------------------------------------------------------------------

W = 760  # SVG coordinate width; the SVG scales to its container.


def bar_path(x: float, y0: float, y1: float, width: float, r: float = 4) -> str:
    """A vertical bar from the baseline y0 to y1, rounded only at the data end."""
    top, bottom = min(y0, y1), max(y0, y1)
    r = min(r, (bottom - top), width / 2)
    if y1 < y0:  # grows upwards
        return (f"M{x:.1f},{bottom:.1f} V{top + r:.1f} Q{x:.1f},{top:.1f} {x + r:.1f},{top:.1f} "
                f"H{x + width - r:.1f} Q{x + width:.1f},{top:.1f} {x + width:.1f},{top + r:.1f} V{bottom:.1f} Z")
    return (f"M{x:.1f},{top:.1f} V{bottom - r:.1f} Q{x:.1f},{bottom:.1f} {x + r:.1f},{bottom:.1f} "
            f"H{x + width - r:.1f} Q{x + width:.1f},{bottom:.1f} {x + width:.1f},{bottom - r:.1f} V{top:.1f} Z")


def hbar_path(x0: float, x1: float, y: float, height: float, r: float = 4) -> str:
    """A horizontal bar from the baseline x0 to x1, rounded only at the data end."""
    left, right = min(x0, x1), max(x0, x1)
    r = min(r, (right - left), height / 2)
    if x1 >= x0:
        return (f"M{left:.1f},{y:.1f} H{right - r:.1f} Q{right:.1f},{y:.1f} {right:.1f},{y + r:.1f} "
                f"V{y + height - r:.1f} Q{right:.1f},{y + height:.1f} {right - r:.1f},{y + height:.1f} H{left:.1f} Z")
    return (f"M{right:.1f},{y:.1f} H{left + r:.1f} Q{left:.1f},{y:.1f} {left:.1f},{y + r:.1f} "
            f"V{y + height - r:.1f} Q{left:.1f},{y + height:.1f} {left + r:.1f},{y + height:.1f} H{right:.1f} Z")


def line_chart(dates: list[date], series: list[tuple[str, list[float], str]], title: str) -> str:
    """Lines over time on one axis, with a crosshair tooltip per date."""
    h, left, right, top, bottom = 320, 64, 120, 16, 36
    pw, ph = W - left - right, h - top - bottom
    values = [v for _, vs, _ in series for v in vs if v is not None]
    ticks = nice_ticks(min(0, min(values)), max(values))
    lo, hi = ticks[0], ticks[-1]
    t0, t1 = dates[0].toordinal(), dates[-1].toordinal()

    def x(d: date) -> float:
        return left + (d.toordinal() - t0) / max(1, t1 - t0) * pw

    def y(v: float) -> float:
        return top + ph - (v - lo) / (hi - lo) * ph

    out = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{esc(title)}">']
    for t in ticks:
        out.append(f'<line class="grid" x1="{left}" x2="{left + pw}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>')
        out.append(f'<text class="tick" x="{left - 8}" y="{y(t) + 4:.1f}" text-anchor="end">{esc(compact(t))}</text>')
    # Date labels: first and last, plus evenly spaced ones that keep clear of them.
    shown = [0]
    for i in range(1, len(dates) - 1):
        if x(dates[i]) - x(dates[shown[-1]]) >= 130 and x(dates[-1]) - x(dates[i]) >= 130:
            shown.append(i)
    shown.append(len(dates) - 1)
    for i in shown:
        anchor = "start" if i == 0 else "end" if i == len(dates) - 1 else "middle"
        out.append(f'<text class="tick" x="{x(dates[i]):.1f}" y="{h - 12}" text-anchor="{anchor}">{esc(day(dates[i]))}</text>')
    for name, vs, color in series:
        points = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in zip(dates, vs))
        out.append(f'<polyline class="line" points="{points}" style="stroke:var({color})"/>')
    # End labels: series name and last value, nudged apart only if they collide.
    ends = sorted(((y(vs[-1]), name, vs[-1], color) for name, vs, color in series), key=lambda e: e[0])
    placed: list[float] = []
    for ey, name, v, color in ends:
        ly = max(ey, placed[-1] + 30) if placed else ey
        placed.append(ly)
        ex = x(dates[-1])
        out.append(f'<circle class="dot" cx="{ex:.1f}" cy="{ey:.1f}" r="4" style="fill:var({color})"/>')
        out.append(f'<text class="label" x="{ex + 10:.1f}" y="{ly - 2:.1f}">{esc(name)}</text>')
        out.append(f'<text class="value" x="{ex + 10:.1f}" y="{ly + 13:.1f}">{esc(kr(v))}</text>')
    # Crosshair columns: the whole height between neighbouring dates is the hit target.
    xs = [x(d) for d in dates]
    for i, d in enumerate(dates):
        a = left if i == 0 else (xs[i - 1] + xs[i]) / 2
        b = left + pw if i == len(dates) - 1 else (xs[i] + xs[i + 1]) / 2
        rows = [day(d)] + [f"{kr(vs[i])}::{name}" for name, vs, _ in series]
        out.append(f'<g class="hit col" tabindex="0" data-tip="{tip(*rows)}">'
                   f'<rect x="{a:.1f}" y="{top}" width="{b - a:.1f}" height="{ph}"/>'
                   f'<line class="cross" x1="{xs[i]:.1f}" x2="{xs[i]:.1f}" y1="{top}" y2="{top + ph}"/></g>')
    out.append(f'<line class="axis" x1="{left}" x2="{left + pw}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>')
    out.append("</svg>")
    return "".join(out)


def column_chart(labels: list[str], values: list[float], tips: list[str], title: str) -> str:
    """Columns from a zero baseline, blue up and red down."""
    h, left, right, top, bottom = 260, 52, 12, 20, 36
    pw, ph = W - left - right, h - top - bottom
    ticks = nice_ticks(min(0, min(values)), max(0, max(values)), 4)
    lo, hi = ticks[0], ticks[-1]
    band = pw / len(values)
    width = min(24, band * 0.6)

    def y(v: float) -> float:
        return top + ph - (v - lo) / (hi - lo) * ph

    out = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{esc(title)}">']
    for t in ticks:
        out.append(f'<line class="grid" x1="{left}" x2="{left + pw}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>')
        out.append(f'<text class="tick" x="{left - 8}" y="{y(t) + 4:.1f}" text-anchor="end">{esc(dk(t))} %</text>')
    extremes = {values.index(max(values)), values.index(min(values))}
    for i, (label, v) in enumerate(zip(labels, values)):
        cx = left + band * (i + 0.5)
        color = "--pos" if v >= 0 else "--neg"
        out.append(f'<g class="hit bar" tabindex="0" data-tip="{tips[i]}">'
                   f'<rect x="{cx - band / 2:.1f}" y="{top}" width="{band:.1f}" height="{ph}"/>'
                   f'<path d="{bar_path(cx - width / 2, y(0), y(v), width)}" style="fill:var({color})"/></g>')
        out.append(f'<text class="tick" x="{cx:.1f}" y="{h - 12}" text-anchor="middle">{esc(label)}</text>')
        if i in extremes and v:
            vy = y(v) - 6 if v >= 0 else y(v) + 14
            out.append(f'<text class="value" x="{cx:.1f}" y="{vy:.1f}" text-anchor="middle">{esc(pct(v, 1, True))}</text>')
    out.append(f'<line class="axis" x1="{left}" x2="{left + pw}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>')
    out.append("</svg>")
    return "".join(out)


def hbar_chart(labels: list[str], values: list[float], tips: list[str], title: str,
               value_text, diverging: bool = True) -> str:
    """Horizontal bars with the name above each bar, so long names never clip."""
    row, left, right, top = 40, 4, 110, 4
    h = top + row * len(values) + 4
    pw = W - left - right
    lo, hi = min(0, min(values)), max(0, max(values))
    span = (hi - lo) or 1

    def x(v: float) -> float:
        return left + (v - lo) / span * pw

    out = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{esc(title)}">']
    if lo < 0:
        out.append(f'<line class="axis" x1="{x(0):.1f}" x2="{x(0):.1f}" y1="{top}" y2="{h - 4}"/>')
    for i, (label, v) in enumerate(zip(labels, values)):
        y0 = top + i * row
        color = ("--pos" if v >= 0 else "--neg") if diverging else "--series-1"
        out.append(f'<g class="hit bar" tabindex="0" data-tip="{tips[i]}">'
                   f'<rect x="0" y="{y0}" width="{W}" height="{row}"/>'
                   f'<path d="{hbar_path(x(0), x(v), y0 + 20, 12)}" style="fill:var({color})"/></g>')
        out.append(f'<text class="label" x="{left}" y="{y0 + 14}">{esc(label)}</text>')
        vx = max(x(0), x(v)) + 8
        out.append(f'<text class="value" x="{vx:.1f}" y="{y0 + 30}">{esc(value_text(v))}</text>')
    out.append("</svg>")
    return "".join(out)


def stacked_bar(parts: list[tuple[str, float, str]], title: str) -> str:
    """One bar split into parts with 2px gaps, and a legend with values below."""
    total = sum(v for _, v, _ in parts if v > 0) or 1
    h, gap = 28, 2
    out = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{esc(title)}">']
    shown = [(n, v, c) for n, v, c in parts if v > 0]
    x = 0.0
    usable = W - gap * (len(shown) - 1)
    for i, (name, v, color) in enumerate(shown):
        w = v / total * usable
        r = 4 if i in (0, len(shown) - 1) else 0
        out.append(f'<g class="hit bar" tabindex="0" data-tip="{tip(name, f"{kr(v)}::markedsværdi", f"{pct(v / total * 100)}::andel")}">'
                   f'<rect x="{x:.1f}" y="0" width="{max(w, 1):.1f}" height="{h}" rx="{r}" style="fill:var({color})"/></g>')
        x += w + gap
    out.append("</svg>")
    legend = "".join(
        f'<li><span class="swatch" style="background:var({c})"></span><span class="lname">{esc(n)}</span>'
        f'<span class="lvalue">{esc(kr(v))} · {esc(pct(v / total * 100))}</span></li>'
        for n, v, c in parts
    )
    return "".join(out) + f'<ul class="legend">{legend}</ul>'


# --- Page ---------------------------------------------------------------------

CSS = """
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface-1: #fcfcfb; --text-primary: #0b0b0b; --text-secondary: #52514e;
  --text-muted: #6f6e69; --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a; --series-4: #eda100;
  --pos: #2a78d6; --neg: #e34948; --good-text: #006300; --bad-text: #b42323;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface-1: #1a1a19; --text-primary: #f0efec; --text-secondary: #c3c2b7;
    --text-muted: #9a9890; --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500;
    --pos: #3987e5; --neg: #e66767; --good-text: #0ca30c; --bad-text: #e66767;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface-1: #1a1a19; --text-primary: #f0efec; --text-secondary: #c3c2b7;
  --text-muted: #9a9890; --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500;
  --pos: #3987e5; --neg: #e66767; --good-text: #0ca30c; --bad-text: #e66767;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--text-primary);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 960px; margin: 0 auto; padding: 32px 16px 64px; }
header h1 { font-size: 22px; margin: 0 0 4px; font-weight: 600; }
header p { margin: 0; color: var(--text-secondary); }
.hero { margin: 28px 0 8px; }
.hero .value { font-size: 56px; font-weight: 600; line-height: 1.1; }
.hero .sub { color: var(--text-secondary); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 24px 0; }
.tile, .card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; }
.tile { padding: 14px 16px; }
.tile .label { color: var(--text-secondary); font-size: 13px; }
.tile .value { font-size: 22px; font-weight: 600; }
.tile .note { color: var(--text-muted); font-size: 12px; }
.card { padding: 20px; margin: 16px 0; overflow: hidden; }
.card h2 { font-size: 17px; margin: 0 0 2px; font-weight: 600; }
.card .desc { color: var(--text-secondary); margin: 0 0 14px; font-size: 14px; }
.legend-inline { display: flex; gap: 16px; flex-wrap: wrap; margin: 0 0 8px; padding: 0; list-style: none;
  color: var(--text-secondary); font-size: 13px; }
.key { display: inline-block; width: 14px; height: 2px; vertical-align: middle; margin-right: 6px; border-radius: 1px; }
svg { display: block; width: 100%; height: auto; overflow: visible; }
svg text { font-family: inherit; }
.grid { stroke: var(--grid); stroke-width: 1; }
.axis { stroke: var(--axis); stroke-width: 1; }
.tick { fill: var(--text-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.label { fill: var(--text-secondary); font-size: 13px; }
.value { fill: var(--text-primary); font-size: 13px; font-weight: 600; }
.line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.dot { stroke: var(--surface-1); stroke-width: 2; }
.hit > rect:first-child { fill: transparent; }
.hit:focus { outline: none; }
.cross { stroke: var(--text-muted); stroke-width: 1; opacity: 0; }
.col:hover .cross, .col:focus .cross { opacity: 1; }
.bar:hover path, .bar:focus path, .bar:hover rect + rect { opacity: 0.8; }
.bar:focus-visible path { stroke: var(--text-primary); stroke-width: 1; }
.legend { list-style: none; padding: 0; margin: 14px 0 0; display: grid; gap: 6px; }
.legend li { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.swatch { width: 12px; height: 12px; border-radius: 3px; flex: none; }
.lname { color: var(--text-secondary); }
.lvalue { margin-left: auto; font-variant-numeric: tabular-nums; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 7px 6px; border-bottom: 1px solid var(--grid); text-align: right; white-space: nowrap; }
th:first-child, td:first-child, th.text, td.text { text-align: left; }
td:first-child { white-space: normal; min-width: 150px; }
th { color: var(--text-secondary); font-weight: 600; white-space: normal; vertical-align: bottom;
  position: sticky; top: 0; background: var(--surface-1); }
td { font-variant-numeric: tabular-nums; }
.pos { color: var(--good-text); } .neg { color: var(--bad-text); }
details summary { cursor: pointer; color: var(--text-secondary); margin-top: 12px; }
.footnote { color: var(--text-muted); font-size: 12px; margin-top: 24px; }
#tooltip { position: fixed; pointer-events: none; background: var(--surface-1); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 13px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12); display: none; max-width: 320px; z-index: 10; }
#tooltip .head { color: var(--text-secondary); margin-bottom: 4px; }
#tooltip .row { display: flex; gap: 8px; align-items: baseline; }
#tooltip .row strong { font-variant-numeric: tabular-nums; }
#tooltip .row span { color: var(--text-secondary); }
"""

JS = """
const tt = document.getElementById('tooltip');
function show(el, x, y) {
  tt.replaceChildren();
  const rows = el.dataset.tip.split('|');
  const head = document.createElement('div'); head.className = 'head'; head.textContent = rows[0]; tt.append(head);
  for (const r of rows.slice(1)) {
    const [value, label] = r.split('::');
    const row = document.createElement('div'); row.className = 'row';
    const s = document.createElement('strong'); s.textContent = value; row.append(s);
    if (label) { const l = document.createElement('span'); l.textContent = label; row.append(l); }
    tt.append(row);
  }
  tt.style.display = 'block';
  const w = tt.offsetWidth, h = tt.offsetHeight;
  tt.style.left = Math.min(x + 14, innerWidth - w - 8) + 'px';
  tt.style.top = Math.max(8, y - h - 12) + 'px';
}
document.querySelectorAll('[data-tip]').forEach(el => {
  el.addEventListener('pointermove', e => show(el, e.clientX, e.clientY));
  el.addEventListener('pointerleave', () => { tt.style.display = 'none'; });
  el.addEventListener('focus', () => { const r = el.getBoundingClientRect(); show(el, r.left + r.width / 2, r.top); });
  el.addEventListener('blur', () => { tt.style.display = 'none'; });
});
"""


def signed_class(v) -> str:
    return "pos" if v is not None and v > 0 else "neg" if v is not None and v < 0 else ""


def render(data: dict) -> str:
    s = data["summary"]
    total = next(a for a in data["accounts"] if a["account"] == "I alt")

    tiles = [
        ("Kontoens værdi", kr(s["end_value"]), f"pr. {day(s['end_date'])}"),
        ("Nettoindbetalt", kr(s["net_deposits"]), "indbetalinger minus udbetalinger"),
        ("Gevinst/tab", kr(s["total_gain_loss"]), "værdi minus nettoindbetalt"),
        ("Årligt pengevægtet afkast", pct(total["annual_return_pct"], 1, True), "egen beregning (XIRR)"),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="label">{esc(l)}</div><div class="value">{esc(v)}</div>'
        f'<div class="note">{esc(n)}</div></div>' for l, v, n in tiles
    )

    vs = data["value_series"]
    value_chart = line_chart(
        [p["date"] for p in vs],
        [("Kontoens værdi", [p["value"] for p in vs], "--series-1"),
         ("Nettoindbetalt", [p["net_deposits"] for p in vs], "--series-2")],
        "Kontoens værdi og nettoindbetalt over tid",
    )

    periods = data["periods"]
    period_labels = [p["period"] + ("*" if p["partial"] else "") for p in periods]
    period_chart = column_chart(
        period_labels,
        [p["return_pct"] for p in periods],
        [tip(p["period"] + (" (delvis periode)" if p["partial"] else ""),
             f"{pct(p['return_pct'], 1, True)}::tidsvægtet afkast",
             f"{kr(p['gain_loss'])}::gevinst/tab") for p in periods],
        "Tidsvægtet afkast pr. periode",
    )

    by_instrument = (
        pd.DataFrame(data["instruments"])
        .groupby("instrument", as_index=False)
        .agg(gain_loss=("gain_loss", "sum"), invested=("invested", "sum"), market_value=("market_value", "sum"))
        .sort_values("gain_loss", ascending=False)
    )
    gain_chart = hbar_chart(
        by_instrument["instrument"].tolist(),
        by_instrument["gain_loss"].tolist(),
        [tip(r.instrument, f"{kr(r.gain_loss)}::gevinst/tab", f"{kr(r.invested)}::investeret",
             f"{kr(r.market_value)}::markedsværdi i dag") for r in by_instrument.itertuples()],
        "Gevinst/tab pr. papir",
        kr,
    )

    alloc_colors = ["--series-1", "--series-2", "--series-3", "--series-4"]
    allocation = stacked_bar(
        [(a["name"], a["value"], alloc_colors[i % 4]) for i, a in enumerate(data["allocation"])],
        "Fordeling af kontoens værdi",
    )

    holdings = sorted(data["holdings"], key=lambda h: -h["market_value"])
    top, rest = holdings[:10], holdings[10:]
    if rest:
        top.append({"instrument": f"Øvrige {len(rest)} papirer",
                    "market_value": sum(h["market_value"] for h in rest),
                    "weight_pct": sum(h["weight_pct"] for h in rest)})
    weight_chart = hbar_chart(
        [h["instrument"] for h in top],
        [h["weight_pct"] for h in top],
        [tip(h["instrument"], f"{pct(h['weight_pct'])}::andel af kontoens værdi",
             f"{kr(h['market_value'])}::markedsværdi") for h in top],
        "Største beholdninger",
        lambda v: pct(v),
        diverging=False,
    )

    def table(rows: list[dict], columns: list[tuple[str, str, object, bool]]) -> str:
        head = "".join(f'<th class="{"text" if not numeric else ""}">{esc(t)}</th>' for t, _, _, numeric in columns)
        body = []
        for r in rows:
            cells = []
            for _, key, fmt, numeric in columns:
                v = r.get(key)
                signed = ("gain_loss", "return_pct", "annual_return_pct", "return_on_net_deposits_pct")
                cls = signed_class(v) if numeric and key in signed else ""
                cells.append(f'<td class="{cls if numeric else "text"}">{esc(fmt(v) if fmt else (v if v is not None else "–"))}</td>')
            body.append("<tr>" + "".join(cells) + "</tr>")
        return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'

    instrument_table = table(
        sorted(data["instruments"], key=lambda r: (r["account"], -r["gain_loss"])),
        [("Papir", "instrument", None, False), ("Konto", "account", None, False), ("Status", "status", None, False),
         ("Investeret", "invested", kr, True), ("Udbytte", "dividends", kr, True), ("Omkostninger", "costs", kr, True),
         ("Markedsværdi", "market_value", kr, True), ("Gevinst/tab", "gain_loss", kr, True),
         ("Afkast", "return_pct", lambda v: pct(v, 1, True), True),
         ("Årligt (XIRR)", "annual_return_pct", lambda v: pct(v, 1, True), True)],
    )
    account_table = table(
        data["accounts"],
        [("Konto", "account", None, False), ("Indbetalt", "deposits", kr, True), ("Udbetalt", "withdrawals", kr, True),
         ("Værdi i dag", "value", kr, True), ("Gevinst/tab", "gain_loss", kr, True),
         ("Afkast af nettoindbetalt", "return_on_net_deposits_pct", lambda v: pct(v, 1, True), True),
         ("Årligt (XIRR)", "annual_return_pct", lambda v: pct(v, 1, True), True)],
    )
    period_table = table(
        [{**p, "period": p["period"] + (" (delvis)" if p["partial"] else "")} for p in periods],
        [("Periode", "period", None, False), ("Tidsvægtet afkast", "return_pct", lambda v: pct(v, 1, True), True),
         ("Gevinst/tab", "gain_loss", kr, True), ("Omkostninger", "costs", kr, True)],
    )
    value_table = table(
        vs, [("Dato", "date", day, False), ("Kontoens værdi", "value", kr, True),
             ("Nettoindbetalt", "net_deposits", kr, True)],
    )

    title = data.get("title", "Porteføljeoversigt")
    return f"""<!doctype html>
<html lang="da">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<header>
  <h1>{esc(title)}</h1>
  <p>{esc(day(s['start_date']))} – {esc(day(s['end_date']))} · alle konti · DKK</p>
</header>

<section class="hero">
  <div class="sub">Samlet tidsvægtet afkast</div>
  <div class="value">{esc(pct(s['total_return_pct'], 1, True))}</div>
  <div class="sub">{esc(kr(s['total_gain_loss']))} i gevinst/tab på {esc(kr(s['net_deposits']))} nettoindbetalt</div>
</section>

<div class="tiles">{tiles_html}</div>

<section class="card">
  <h2>Kontoens værdi over tid</h2>
  <p class="desc">Afstanden mellem de to linjer er din gevinst eller dit tab.</p>
  <ul class="legend-inline">
    <li><span class="key" style="background:var(--series-1)"></span>Kontoens værdi</li>
    <li><span class="key" style="background:var(--series-2)"></span>Nettoindbetalt</li>
  </ul>
  {value_chart}
  <details><summary>Vis som tabel</summary>{value_table}</details>
</section>

<section class="card">
  <h2>Afkast pr. periode</h2>
  <p class="desc">Tidsvægtet afkast, som Saxo beregner det. * = delvis periode.</p>
  {period_chart}
  <details><summary>Vis som tabel</summary>{period_table}</details>
</section>

<section class="card">
  <h2>Gevinst/tab pr. papir</h2>
  <p class="desc">Markedsværdi i dag plus alt bogført på papiret: køb, salg, udbytte og omkostninger. Begge konti lagt sammen.</p>
  {gain_chart}
</section>

<section class="card">
  <h2>Fordeling</h2>
  <p class="desc">Hvad kontoens værdi består af i dag.</p>
  {allocation}
  <h2 style="margin-top:24px">Største beholdninger</h2>
  <p class="desc">Andel af kontoens samlede værdi.</p>
  {weight_chart}
</section>

<section class="card">
  <h2>Konti</h2>
  <p class="desc">Pengevægtet afkast (XIRR) tager højde for, hvornår du har sat penge ind.</p>
  {account_table}
</section>

<section class="card">
  <h2>Alle papirer</h2>
  <p class="desc">Afkast = gevinst/tab i forhold til det investerede beløb. Årligt (XIRR) mangler, hvor perioden er for kort.</p>
  {instrument_table}
</section>

<p class="footnote">Lavet lokalt ud fra Saxos eksporterede rapporter. Siden henter intet fra internettet.
Gevinst/tab pr. papir kan afvige lidt fra Saxos egne tal ved udbytteskat og selskabsbegivenheder.</p>
</main>
<div id="tooltip" role="tooltip"></div>
<script>{JS}</script>
</body>
</html>
"""


# --- Data ---------------------------------------------------------------------

def build_data(portfolio: dict[str, pd.DataFrame], transactions: dict[str, pd.DataFrame],
               instruments: pd.DataFrame, accounts: pd.DataFrame) -> dict:
    s = portfolio["summary"].iloc[0]
    av = portfolio["account_value"]
    trades = transactions["trades"]
    external = trades[~trades["is_total"] & trades["event_type"].isin({"Indbetaling", "Udbetaling"})]
    value_series = [
        {"date": d, "value": v,
         "net_deposits": float(external.loc[external["value_date"] <= d, "booked_amount"].sum())}
        for d, v in zip(av["date"], av["account_value"])
    ]
    overview = portfolio["holdings_overview"]
    overview = overview[~overview["is_total"]]
    positions = portfolio["positions"]
    positions = positions[~positions["is_total"]]
    holdings = (
        positions.groupby("instrument", as_index=False)
        .agg(market_value=("market_value", "sum"), weight_pct=("weight_pct", "sum"))
        .to_dict("records")
    )
    return {
        "summary": s.to_dict(),
        "value_series": value_series,
        "periods": portfolio["period_returns"].query("period != 'Total'").to_dict("records"),
        "instruments": instruments.where(instruments.notna(), None).to_dict("records"),
        "accounts": accounts.where(accounts.notna(), None).to_dict("records"),
        "allocation": [{"name": r["product"], "value": r["market_value"]} for _, r in overview.iterrows()],
        "holdings": holdings,
    }


def demo_data() -> dict:
    """Made-up numbers for trying the page without real data."""
    start, end = date(2024, 1, 1), date(2025, 12, 31)
    dates = [start + timedelta(days=round(i * (end - start).days / 9)) for i in range(10)]
    deposits = [0, 20000, 40000, 50000, 60000, 70000, 80000, 90000, 100000, 100000]
    values = [0, 20500, 41000, 49000, 63000, 75000, 83000, 97000, 108000, 112000]
    periods = [("K1-2024", True, 1.2), ("K2-2024", False, 3.4), ("K3-2024", False, -2.1),
               ("K4-2024", False, 5.0), ("K1-2025", False, 2.2), ("K2-2025", False, -4.3),
               ("K3-2025", False, 6.1), ("K4-2025", True, 3.0)]
    names = ["Fake Industries A/S", "Example Bank A/S", "Sample Global Index KL", "Demo Pharma B A/S",
             "Placeholder Tech Inc.", "Test Energy ASA", "Mock Shipping A/S", "Dummy Retail Corp."]
    gains = [6200, 3100, 2500, 1500, 800, -300, -900, -1000]
    instruments = [
        {"account": "Konto 1" if i % 2 else "Aktiesparekonto", "instrument": n,
         "status": "lukket" if i == 7 else "åben", "invested": 10000.0 + 1000 * i,
         "dividends": 100.0 * (i % 3), "costs": 29.0, "market_value": 0.0 if i == 7 else 10000.0 + 1000 * i + g,
         "gain_loss": float(g), "return_pct": g / (10000 + 1000 * i) * 100,
         "annual_return_pct": g / (10000 + 1000 * i) * 50 if i != 4 else None}
        for i, (n, g) in enumerate(zip(names, gains))
    ]
    return {
        "title": "Porteføljeoversigt (demo med opdigtede tal)",
        "summary": {"start_date": start, "end_date": end, "start_value": 0.0, "total_gain_loss": 12000.0,
                    "net_deposits": 100000.0, "end_value": 112000.0, "change_in_value": 112000.0,
                    "total_return_pct": 15.4},
        "value_series": [{"date": d, "value": float(v), "net_deposits": float(n)} for d, v, n in zip(dates, values, deposits)],
        "periods": [{"period": p, "partial": part, "return_pct": r, "gain_loss": r * 900, "costs": -40.0}
                    for p, part, r in periods],
        "instruments": instruments,
        "accounts": [
            {"account": "Aktiesparekonto", "deposits": 60000.0, "withdrawals": 0.0, "value": 68000.0,
             "gain_loss": 8000.0, "return_on_net_deposits_pct": 13.3, "annual_return_pct": 9.8},
            {"account": "Konto 1", "deposits": 40000.0, "withdrawals": 0.0, "value": 44000.0,
             "gain_loss": 4000.0, "return_on_net_deposits_pct": 10.0, "annual_return_pct": 7.1},
            {"account": "I alt", "deposits": 100000.0, "withdrawals": 0.0, "value": 112000.0,
             "gain_loss": 12000.0, "return_on_net_deposits_pct": 12.0, "annual_return_pct": 8.7},
        ],
        "allocation": [{"name": "Aktier", "value": 80000.0}, {"name": "Investeringsforeninger", "value": 25000.0},
                       {"name": "Kontanter", "value": 6500.0}, {"name": "Akkumulerede ikke-bogførte beløb", "value": 500.0}],
        "holdings": [{"instrument": n, "market_value": 8000.0 - 600 * i, "weight_pct": (8000.0 - 600 * i) / 1120}
                     for i, n in enumerate(names[:7] + [f"Other Holding {k}" for k in range(1, 7)])],
    }


def main(argv: list[str]) -> int:
    out = Path("output")
    out.mkdir(exist_ok=True)
    if "--demo" in argv:
        path = out / "report_demo.html"
        path.write_text(render(demo_data()), encoding="utf-8")
        print(f"Demo report -> {path}")
        return 0

    from datetime import date as _date

    from saxobank.portfolio_report import parse_portfolio_report
    from saxobank.returns import REPORT_DATES, _newest, account_returns, instrument_returns
    from saxobank.transaction_report import parse_transaction_report

    transaction_path = _newest("TransactionBalance_*.pdf")
    m = REPORT_DATES.search(transaction_path.name)
    end = _date.fromisoformat(m.group(2)) if m else _date.today()
    transactions = parse_transaction_report(transaction_path)
    portfolio = parse_portfolio_report(_newest("Portfolio_*.pdf"))
    instruments = instrument_returns(transactions["trades"], transactions["positions"], end)
    accounts = account_returns(transactions["trades"], transactions["positions"], transactions["bookings"], end)
    data = build_data(portfolio, transactions, instruments, accounts)

    last = data["value_series"][-1]["net_deposits"]
    ok = abs(last - data["summary"]["net_deposits"]) <= 1
    print(f"[{'OK' if ok else 'FEJL'}] Nettoindbetalt i grafen ender på nettoindbetalingerne i porteføljerapporten")
    path = out / "report.html"
    path.write_text(render(data), encoding="utf-8")
    print(f"Report -> {path}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
