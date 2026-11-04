"""HTML/SVG/Plotly building blocks for the Streamlit pages."""
from __future__ import annotations

import difflib
import html
import math

import pandas as pd

from fed_decoder.analysis.diff import redline, sentences
from fed_decoder.llm.guardrail import quote_in
from fed_decoder.ui import theme

E = html.escape


def fmt_pct(x: float) -> str:
    return f"{x:.2f}"


def fmt_range(lo: float, hi: float) -> str:
    if lo is None or hi is None or (isinstance(hi, float) and math.isnan(hi)):
        return "n/a"
    return f"{fmt_pct(hi)}%" if lo == hi else f"{fmt_pct(lo)}–{fmt_pct(hi)}%"


def facts_html(decision, meeting_date: str) -> str:
    bps = decision.change_bps
    move = "0 bp" if bps == 0 else f"{'+' if bps > 0 else '−'}{abs(bps)} bp"
    vote = f"{decision.votes_for}–{decision.votes_against}" if decision.votes_for is not None else "not reported"
    dis = ", ".join(n.split()[-1] if not n.endswith("Jr.") else n.split()[-2].rstrip(",") for n in decision.dissenters) or "none"
    cells = [
        ("Decision", decision.direction.capitalize()),
        ("Change", move),
        ("Target", fmt_range(decision.target_low, decision.target_high)),
        ("Vote", vote),
        ("Dissents", dis),
    ]
    return '<div class="facts">' + "".join(
        f'<div><div class="kicker">{E(k)}</div><div class="v{" mono" if k in ("Change", "Target", "Vote") else ""}" style="{"font-size:19px;padding-top:4px" if k in ("Dissents", "Decision") else ""}">{E(v)}</div></div>'
        for k, v in cells
    ) + "</div>"


def _explain_for(sentence_new: str, sentence_old: str, changes) -> str:
    for c in changes:
        q = c.quote
        if (sentence_new and (quote_in(q, sentence_new) or quote_in(sentence_new, q))) or (
            sentence_old and (quote_in(q, sentence_old) or quote_in(sentence_old, q))
        ):
            return c.explanation
    return ""


def _wrap(inner: str, tip: str) -> str:
    if not tip:
        return inner
    return f'<span class="chg" tabindex="0">{inner}<span class="tip">{E(tip)}</span></span>'


def redline_html(old: str | None, new: str, changes) -> str:
    """Sentence-aligned redline. Changed sentences carry a hover explanation."""
    if not old:
        return '<div class="redline">' + "".join(f"<p>{E(p)}</p>" for p in new.split("\n\n")) + "</div>"
    out_paras = []
    # Work paragraph-agnostic: align sentences across the whole statement.
    a, b = sentences(old), sentences(new)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    pieces: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            pieces += [E(s) for s in b[j1:j2]]
            continue
        olds, news = list(a[i1:i2]), list(b[j1:j2])
        used = set()
        for n in news:
            best, br = None, 0.0
            for k, o in enumerate(olds):
                if k in used:
                    continue
                r = difflib.SequenceMatcher(None, o, n).ratio()
                if r > br:
                    best, br = k, r
            if best is not None and br >= 0.5:
                used.add(best)
                o = olds[best]
                inner = "".join(
                    E(op.text) if op.op == "equal" else f"<del>{E(op.text)}</del>" if op.op == "delete" else f"<ins>{E(op.text)}</ins>"
                    for op in redline(o, n)
                )
                pieces.append(_wrap(inner, _explain_for(n, o, changes)))
            else:
                pieces.append(_wrap(f"<ins>{E(n)}</ins>", _explain_for(n, "", changes)))
        for k, o in enumerate(olds):
            if k not in used:
                pieces.append(_wrap(f"<del>{E(o)}</del>", _explain_for("", o, changes)))
    # chunk into readable paragraphs of ~4 sentences
    for i in range(0, len(pieces), 4):
        out_paras.append("<p>" + " ".join(pieces[i : i + 4]) + "</p>")
    return '<div class="redline">' + "".join(out_paras) + "</div>"


def tone_dial_svg(score: float) -> str:
    """Single needle from dove (-2, left) to hawk (+2, right)."""
    s = max(-2.0, min(2.0, float(score)))
    cx, cy, r = 160, 150, 120
    ang = math.pi * (1 - (s + 2) / 4)  # pi (left) .. 0 (right)
    nx, ny = cx + (r - 14) * math.cos(ang), cy - (r - 14) * math.sin(ang)
    ticks = []
    for v in (-2, -1, 0, 1, 2):
        a = math.pi * (1 - (v + 2) / 4)
        x1, y1 = cx + r * math.cos(a), cy - r * math.sin(a)
        x2, y2 = cx + (r - 10) * math.cos(a), cy - (r - 10) * math.sin(a)
        ticks.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{theme.MUTED}" stroke-width="1"/>')
    label = "Hawkish" if s > 0.3 else "Dovish" if s < -0.3 else "Balanced"
    return f"""
<svg viewBox="0 0 320 190" width="100%" style="max-width:360px" role="img" aria-label="Tone {s:+.1f} on a scale from -2 dovish to +2 hawkish">
  <path d="M {cx - r} {cy} A {r} {r} 0 0 1 {cx + r} {cy}" fill="none" stroke="{theme.RULE}" stroke-width="10" stroke-linecap="round"/>
  <path d="M {cx - r} {cy} A {r} {r} 0 0 1 {cx - r * math.cos(math.pi / 4):.1f} {cy - r * math.sin(math.pi / 4):.1f}" fill="none" stroke="{theme.DOVE}" stroke-opacity=".35" stroke-width="10" stroke-linecap="round"/>
  <path d="M {cx + r * math.cos(math.pi / 4):.1f} {cy - r * math.sin(math.pi / 4):.1f} A {r} {r} 0 0 1 {cx + r} {cy}" fill="none" stroke="{theme.ACCENT}" stroke-opacity=".35" stroke-width="10" stroke-linecap="round"/>
  {''.join(ticks)}
  <line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{theme.INK}" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="{cx}" cy="{cy}" r="5" fill="{theme.INK}"/>
  <text x="{cx - r}" y="{cy + 24}" font-family="Inter, sans-serif" font-size="13" fill="{theme.MUTED}" text-anchor="middle">Dove</text>
  <text x="{cx + r}" y="{cy + 24}" font-family="Inter, sans-serif" font-size="13" fill="{theme.MUTED}" text-anchor="middle">Hawk</text>
  <text x="{cx}" y="{cy - 40}" font-family="IBM Plex Mono, monospace" font-size="26" fill="{theme.INK}" text-anchor="middle">{s:+.1f}</text>
  <text x="{cx}" y="{cy + 26}" font-family="Inter, sans-serif" font-size="14" fill="{theme.INK}" text-anchor="middle">{label}</text>
</svg>"""


def quotes_html(tone_quotes) -> str:
    return "".join(f'<div class="quote {E(q.direction)}">{E(q.quote)}<div class="tag">{E(q.direction)}</div></div>' for q in tone_quotes)


def cards_html(items: list[dict]) -> str:
    """items: {topic, number, text}"""
    return '<div class="cards">' + "".join(
        f'<div class="card"><div class="t">{E(i["topic"])}</div><div class="n">{E(i.get("number") or "")}</div><div class="s">{E(i["text"])}</div></div>'
        for i in items
    ) + "</div>"


def prob_bars(p: dict) -> str:
    rows = []
    for k in ("hold", "cut", "hike"):
        v = p[k]
        rows.append(
            f'<div style="display:grid;grid-template-columns:56px 1fr 56px;gap:12px;align-items:center;margin:6px 0">'
            f'<span>{k.capitalize()}</span><div class="bar"><span style="width:{v * 100:.0f}%"></span></div>'
            f'<span class="mono" style="text-align:right">{v * 100:.0f}%</span></div>'
        )
    return "".join(rows)


def footer_html(text: str) -> str:
    return f'<div class="footer">{E(text)}</div>'


def timeline_fig(gt: pd.DataFrame, tones: dict[str, float], height: int = 460):
    import plotly.graph_objects as go

    from fed_decoder.data import store

    hi = store.series("DFEDTARU")
    single = store.series("DFEDTAR")
    lo = store.series("DFEDTARL")
    upper = pd.concat([single[single.index < "2008-12-16"], hi]).loc["2000-01-01":]
    lower = pd.concat([single[single.index < "2008-12-16"], lo]).loc["2000-01-01":]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=lower.index, y=lower.values, mode="lines", line=dict(width=0, shape="hv"), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=upper.index, y=upper.values, mode="lines", line=dict(color=theme.INK, width=2, shape="hv"),
                             fill="tonexty", fillcolor="rgba(28,27,25,0.08)", hoverinfo="skip", name="Target range"))
    d = gt.copy()
    d["tone"] = d["meeting_date"].dt.strftime("%Y-%m-%d").map(tones)
    d["label"] = d.apply(lambda r: f"{r['meeting_date']:%b %d, %Y}<br>{r['direction'].capitalize()} {r['change_bps']:+d} bp → {fmt_range(r['target_low'], r['target_high'])}<br>Tone {r['tone']:+.1f}", axis=1)
    fig.add_trace(
        go.Scatter(
            x=d["meeting_date"], y=d["target_high"], mode="markers", name="Meeting (color = tone)",
            customdata=d["meeting_date"].dt.strftime("%Y-%m-%d"), text=d["label"], hovertemplate="%{text}<extra></extra>",
            marker=dict(size=10, color=d["tone"], cmin=-2, cmax=2,
                        colorscale=[[0, theme.DOVE], [0.5, theme.NEUTRAL], [1, theme.ACCENT]],
                        line=dict(color=theme.PAPER, width=2),
                        colorbar=dict(title=dict(text="Tone", font=dict(size=13)), tickvals=[-2, 0, 2], ticktext=["Dove −2", "0", "Hawk +2"], thickness=10, len=0.6, outlinewidth=0, tickfont=dict(size=13))),
        )
    )
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor=theme.PAPER, plot_bgcolor=theme.PAPER,
        font=dict(family="Inter, sans-serif", size=14, color=theme.INK), hovermode="closest", showlegend=False,
        hoverlabel=dict(bgcolor=theme.INK, font=dict(color=theme.PAPER, family="Inter, sans-serif", size=14)),
        xaxis=dict(showgrid=False, linecolor=theme.RULE, tickfont=dict(size=13)),
        yaxis=dict(title=dict(text="Fed funds target, %", font=dict(size=13)), gridcolor="#ECE8DE", zeroline=False, tickfont=dict(family="IBM Plex Mono", size=13)),
        clickmode="event+select",
    )
    return fig
