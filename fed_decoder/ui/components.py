"""HTML / Plotly building blocks. Presentation only: every number shown is
passed in from the data and calculation layers."""
from __future__ import annotations

import difflib
import html
import math
import re

import pandas as pd

from fed_decoder.analysis.diff import redline, sentences
from fed_decoder.llm.guardrail import quote_in
from fed_decoder.ui import theme

E = html.escape

# Plain-language definitions, opened by tapping a term (works without hover).
GLOSSARY = {
    "federal funds rate": "The interest rate banks charge each other for overnight loans. The Fed sets a target range for it, and most short-term borrowing costs follow it.",
    "target range": "The band the Fed wants the federal funds rate to stay inside, such as 3.75% to 4%. Since 2008 the Fed has set a range rather than a single number.",
    "basis points": "Hundredths of a percentage point. 25 basis points is a quarter of a point, so a rate going from 4% to 4.25%.",
    "hawkish": "Leaning toward higher interest rates, usually because inflation is the bigger worry.",
    "dovish": "Leaning toward lower interest rates, usually because jobs or growth are the bigger worry.",
    "dissented": "Voted against the decision. Dissents show the committee was not unanimous and hint at where the debate is going.",
    "FOMC": "The Federal Open Market Committee: the 12 voting members who set the Fed's interest rate target, meeting eight times a year.",
    "10-year Treasury": "The interest rate the US government pays to borrow for ten years. Mortgage rates follow it more closely than they follow the Fed.",
}


def define(text_html: str, terms: list[str] | None = None) -> str:
    """Wrap the first occurrence of each glossary term in a tap-to-define element."""
    for term in terms or list(GLOSSARY):
        rx = re.compile(r"(?<![\w>])(" + re.escape(term) + r")(?![\w<])", re.I)
        m = rx.search(text_html)
        if m:
            rep = (f'<label class="term"><input type="checkbox" aria-label="What does {E(term)} mean?">'
                   f'<span class="w">{m.group(1)}</span><span class="d">{E(GLOSSARY[term])}</span></label>')
            text_html = text_html[: m.start()] + rep + text_html[m.end():]
    return text_html


# ---------------------------------------------------------------- formatting
def pct(x: float) -> str:
    return f"{x:.2f}%"


def fmt_range(lo, hi) -> str:
    if lo is None or hi is None or (isinstance(hi, float) and math.isnan(hi)):
        return "not stated"
    return pct(hi) if lo == hi else f"{pct(lo)} to {pct(hi)}"


def points(bps: int) -> str:
    b = abs(int(bps))
    return {25: "a quarter point", 50: "half a point", 75: "three quarters of a point", 100: "a full point"}.get(b, f"{b / 100:.2f} points")


def headline(direction: str, bps: int) -> str:
    if direction == "hold":
        return "The Fed held interest rates steady"
    verb = "cut" if direction == "cut" else "raised"
    return f"The Fed {verb} interest rates by {points(bps)}"


def vote_sentence(d) -> str:
    if d.votes_for is None:
        return ""
    if not d.votes_against:
        return "The decision was unanimous."
    names = ", ".join(d.dissenters[:-1]) + (" and " if len(d.dissenters) > 1 else "") + d.dissenters[-1] if d.dissenters else ""
    who = f" {names} dissented." if names else ""
    return f"The vote was {d.votes_for} to {d.votes_against}.{who}"


def why_it_matters(direction: str) -> str:
    if direction == "hold":
        return ("Rates on credit cards, home equity lines and high-yield savings should stay roughly where they are. "
                "Mortgage rates follow the 10-year Treasury, so they can still move.")
    if direction == "cut":
        return ("Credit card and home equity rates tend to drift down after a cut, and so do savings rates. "
                "Mortgage rates follow the 10-year Treasury, so they may not move with the Fed.")
    return ("Credit card and home equity rates tend to rise after a hike, and savings accounts start paying more. "
            "Mortgage rates follow the 10-year Treasury, so they may not move with the Fed.")


# ---------------------------------------------------------------- decision
def facts_html(d) -> str:
    move = "No change" if d.change_bps == 0 else f"{'+' if d.change_bps > 0 else '−'}{abs(d.change_bps)} basis points"
    vote = f"{d.votes_for} to {d.votes_against}" if d.votes_for is not None else "Not reported"
    cells = [("Target range", fmt_range(d.target_low, d.target_high)), ("Change", move), ("Vote", vote)]
    return '<dl class="facts">' + "".join(f'<div><dt>{k}</dt><dd>{E(v)}</dd></div>' for k, v in cells) + "</dl>"


# ---------------------------------------------------------------- redline
def _explain_for(new_s: str, old_s: str, changes) -> str:
    for c in changes:
        q = c.quote
        if (new_s and (quote_in(q, new_s) or quote_in(new_s, q))) or (old_s and (quote_in(q, old_s) or quote_in(old_s, q))):
            return c.explanation
    return ""


def redline_html(old: str | None, new: str, changes) -> tuple[str, list[dict]]:
    """Sentence-aligned redline with numbered notes listed below the text, so the
    explanations work on touch screens and with keyboards, not just on hover."""
    if not old:
        return '<div class="redline">' + "".join(f"<p>{E(p)}</p>" for p in new.split("\n\n")) + "</div>", []
    a = sentences(old)
    # keep the new statement's own paragraph breaks
    b, b_par = [], []
    for k, para in enumerate(new.split("\n\n")):
        for sent in sentences(para):
            b.append(sent)
            b_par.append(k)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    pieces: list[tuple[int, str]] = []
    notes: list[dict] = []

    def note(text: str, inner: str, was: str = "") -> str:
        if not text:
            return inner
        notes.append({"text": text, "was": was})
        k = len(notes)
        return f'{inner}<sup id="ref{k}"><a href="#note{k}" aria-label="Note {k}">{k}</a></sup>'

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            pieces += [(b_par[j], E(b[j])) for j in range(j1, j2)]
            continue
        olds, news, used = list(a[i1:i2]), list(b[j1:j2]), set()
        par = b_par[j1] if j1 < len(b_par) else (b_par[-1] if b_par else 0)
        for jj, n in enumerate(news):
            par = b_par[j1 + jj]
            best, br = None, 0.0
            for k, o in enumerate(olds):
                if k not in used:
                    r = difflib.SequenceMatcher(None, o, n).ratio()
                    if r > br:
                        best, br = k, r
            if best is not None and br >= 0.5:
                used.add(best)
                inner = "".join(E(op.text) if op.op == "equal" else f"<del>{E(op.text)}</del>" if op.op == "delete" else f"<ins>{E(op.text)}</ins>"
                                for op in redline(olds[best], n))
                pieces.append((par, note(_explain_for(n, olds[best], changes), inner)))
            else:
                pieces.append((par, note(_explain_for(n, "", changes), f"<ins>{E(n)}</ins>")))
        for k, o in enumerate(olds):
            if k not in used:
                pieces.append((par, note(_explain_for("", o, changes), f"<del>{E(o)}</del>")))
    paras, cur, buf = [], None, []
    for par, html_ in pieces + [(-1, "")]:
        if par != cur and buf:
            text = " ".join(buf)
            roster = re.sub(r"<[^>]+>", "", text).lstrip().startswith(("Voting", "Absent"))
            paras.append(f'<p class="roster">{text}</p>' if roster else f"<p>{text}</p>")
            buf = []
        cur = par
        if html_:
            buf.append(html_)
    return '<div class="redline">' + "".join(paras) + "</div>", notes


def notes_html(notes: list[dict]) -> str:
    if not notes:
        return ""
    return '<ol class="notes">' + "".join(f'<li id="note{i}">{E(n["text"])}</li>' for i, n in enumerate(notes, 1)) + "</ol>"


# ---------------------------------------------------------------- tone
def tone_words(score: float) -> tuple[str, str]:
    s = float(score)
    if s >= 1.25:
        return "Clearly hawkish", "hawk"
    if s > 0.3:
        return "Leaning hawkish", "hawk"
    if s <= -1.25:
        return "Clearly dovish", "dove"
    if s < -0.3:
        return "Leaning dovish", "dove"
    return "Balanced", ""


def tone_scale_html(score: float) -> str:
    s = max(-2.0, min(2.0, float(score)))
    left = (s + 2) / 4 * 100
    word, cls = tone_words(s)
    shown = f"{s:+.1f}".replace("-", "−")
    ticks = "".join(f'<i style="left:{p}%"></i>' for p in (0, 25, 50, 75, 100))
    return (f'<div class="scale" role="img" aria-label="Tone {s:+.1f} on a scale from minus 2, dovish, to plus 2, hawkish">'
            f'<div class="read"><span class="{cls}">{word}</span><span class="score">{shown}</span></div>'
            f'<div class="track">{ticks}<b class="pin {cls}" style="left:{left:.1f}%"></b></div>'
            '<div class="ends"><span class="dove">Dovish</span><span>Balanced</span><span class="hawk">Hawkish</span></div></div>')


def quotes_html(tone_quotes) -> str:
    groups = {"hawkish": [], "dovish": [], "other": []}
    for q in tone_quotes:
        groups[q.direction if q.direction in groups else "other"].append(q)
    heads = {"dovish": ("Pointing toward lower rates", "dove"), "hawkish": ("Pointing toward higher rates", "hawk"), "other": ("Neutral", "")}
    out = []
    for key in ("dovish", "hawkish", "other"):
        if groups[key]:
            h, cls = heads[key]
            out.append(f'<div class="quotes"><div class="qh {cls}">{h}</div>' + "".join(f"<p>“{E(q.quote)}”</p>" for q in groups[key]) + "</div>")
    return "".join(out)


# ---------------------------------------------------------------- rows (impacts, economy)
def rows_html(items: list[dict]) -> str:
    """Money rows: the figure leads, the explanation follows. items: {topic, text, number}"""
    return '<div class="rows">' + "".join(
        f'<div class="row"><div class="n">{E(i.get("number") or "")}</div><div><div class="t">{E(i["topic"])}</div><div class="s">{E(i["text"])}</div></div></div>'
        for i in items) + "</div>"


def briefing_html(items: list[dict]) -> str:
    """The economy as a short briefing: a run-in topic, then the sentence."""
    return '<div class="briefing">' + "".join(f'<p><strong>{E(i["topic"])}.</strong> {E(i["text"])}</p>' for i in items) + "</div>"


def odds_html(p: dict) -> str:
    top = max(p, key=p.get)
    rows = []
    for k, lab in (("hold", "Hold"), ("cut", "Cut"), ("hike", "Raise")):
        v = p[k]
        rows.append(f'<div class="o{" top" if k == top else ""}"><span>{lab}</span><div class="bar"><i style="width:{v * 100:.0f}%"></i></div>'
                    f'<span class="fig" style="text-align:right">{v * 100:.0f}%</span></div>')
    return '<div class="odds">' + "".join(rows) + "</div>"


def footer_html(text: str) -> str:
    return f'<div class="footer">{E(text)}</div>'


# ---------------------------------------------------------------- timeline
def timeline_fig(gt: pd.DataFrame, tones: dict[str, float], height: int = 440, selected: str | None = None):
    import plotly.graph_objects as go

    from fed_decoder.data import store

    hi, single, lo = store.series("DFEDTARU"), store.series("DFEDTAR"), store.series("DFEDTARL")
    upper = pd.concat([single[single.index < "2008-12-16"], hi]).loc["2000-01-01":]
    lower = pd.concat([single[single.index < "2008-12-16"], lo]).loc["2000-01-01":]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=lower.index, y=lower.values, mode="lines", line=dict(width=0, shape="hv"), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=upper.index, y=upper.values, mode="lines", line=dict(color=theme.INK, width=1.75, shape="hv"),
                             fill="tonexty", fillcolor="rgba(37,41,35,0.07)", hoverinfo="skip", showlegend=False))
    d = gt.copy()
    d["key"] = d["meeting_date"].dt.strftime("%Y-%m-%d")
    d["tone"] = d["key"].map(tones).fillna(0.0)

    def label(r):
        word, _ = tone_words(r["tone"])
        move = "Held" if r["direction"] == "hold" else f"{'Cut' if r['direction'] == 'cut' else 'Raised'} {abs(r['change_bps'])} bp"
        return f"<b>{r['meeting_date']:%B %-d, %Y}</b><br>{move} · {fmt_range(r['target_low'], r['target_high'])}<br>Tone: {word.lower()}"

    d["label"] = d.apply(label, axis=1)
    d["size"] = d["direction"].map({"hold": 7, "cut": 11, "hike": 11})
    fig.add_trace(go.Scatter(
        x=d["meeting_date"], y=d["target_high"], mode="markers", customdata=d["key"], text=d["label"], hovertemplate="%{text}<extra></extra>",
        marker=dict(size=d["size"], color=d["tone"], cmin=-2, cmax=2, colorscale=[[0, theme.GREEN], [0.5, theme.NEUTRAL], [1, theme.TERRA]],
                    line=dict(color=theme.IVORY, width=1.5), showscale=False),
        selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)),
        showlegend=False))
    if selected:
        s = d[d["key"] == selected]
        if len(s):
            fig.add_trace(go.Scatter(x=s["meeting_date"], y=s["target_high"], mode="markers", hoverinfo="skip", showlegend=False,
                                     marker=dict(size=20, color="rgba(0,0,0,0)", line=dict(color=theme.INK, width=2))))
    fig.update_layout(
        height=height, margin=dict(l=4, r=4, t=8, b=4), paper_bgcolor=theme.IVORY, plot_bgcolor=theme.IVORY,
        font=dict(family="Inter, sans-serif", size=14, color=theme.INK), hovermode="closest", dragmode=False,
        hoverlabel=dict(bgcolor=theme.SURFACE, bordercolor=theme.LINE, font=dict(color=theme.INK, family="Inter, sans-serif", size=14)),
        xaxis=dict(showgrid=False, linecolor=theme.LINE, tickfont=dict(size=13, color=theme.MUTED), fixedrange=True),
        yaxis=dict(ticksuffix="%", gridcolor="#ECE9E1", zeroline=False, tickfont=dict(size=13, color=theme.MUTED), fixedrange=True, rangemode="tozero"),
        clickmode="event+select",
    )
    return fig


# ---------------------------------------------------------------- at-a-glance tiles
def short_move(direction: str, bps: int) -> str:
    if direction == "hold":
        return "Held"
    frac = {25: "¼", 50: "½", 75: "¾", 100: "1"}.get(abs(int(bps)), f"{abs(int(bps)) / 100:.2f}")
    return f"{'Cut' if direction == 'cut' else 'Raised'} {frac} pt"


def step_svg(prev_lo, prev_hi, lo, hi) -> str:
    """Mini step chart: old target range -> new target range."""
    vals = [v for v in (prev_lo, prev_hi, lo, hi) if v is not None]
    top, bot = max(vals) + 0.25, max(0.0, min(vals) - 0.25)
    span = (top - bot) or 1.0
    y = lambda v: 6 + (top - v) / span * 52  # noqa: E731
    change = (hi or 0) - (prev_hi or 0)
    col = theme.TERRA if change > 0 else theme.GREEN if change < 0 else theme.INK
    return (f'<svg viewBox="0 0 140 64" width="140" height="64" aria-hidden="true">'
            f'<rect x="0" y="{y(prev_hi):.1f}" width="60" height="{max(8, y(prev_lo) - y(prev_hi)):.1f}" rx="2" fill="{theme.NEUTRAL}" opacity=".55"/>'
            f'<rect x="80" y="{y(hi):.1f}" width="60" height="{max(8, y(lo) - y(hi)):.1f}" rx="2" fill="{col}" opacity=".9"/>'
            f'<path d="M60 {y(prev_hi):.1f} H70 V{y(hi):.1f} H80" fill="none" stroke="{theme.FAINT}" stroke-width="1.5"/></svg>')


def mini_scale(score: float) -> str:
    s = max(-2.0, min(2.0, float(score)))
    _, cls = tone_words(s)
    return (f'<div class="mscale"><div class="mtrack"><b class="{cls}" style="left:{(s + 2) / 4 * 100:.1f}%"></b></div>'
            '<div class="mends"><span>Dove</span><span>Hawk</span></div></div>')


def odds_bar(p: dict) -> str:
    segs = [("hold", "Hold", theme.NEUTRAL), ("hike", "Raise", theme.TERRA), ("cut", "Cut", theme.GREEN)]
    bar = "".join(f'<i style="width:{p[k] * 100:.1f}%;background:{c}"></i>' for k, _, c in segs if p[k] > 0.005)
    top = max(p, key=p.get)
    legend = " · ".join(f'{lab} {p[k] * 100:.0f}%' for k, lab, _ in segs if k != top)  # the big number already states the top one
    return f'<div class="obar">{bar}</div><div class="tcap">{legend}</div>'


def tile(label: str, big: str, visual: str = "", caption: str = "", big_cls: str = "") -> str:
    return (f'<div class="tile"><div class="tlab">{E(label)}</div><div class="tbig {big_cls}">{E(big)}</div>'
            f'{visual}{f"<div class=tcap>{E(caption)}</div>" if caption else ""}</div>')


def signed_money(x: float, unit: str = "/mo") -> str:
    if abs(x) < 0.005:
        return "$0" + unit
    return f"{'−' if x < 0 else '+'}${abs(x):,.0f}{unit}" if abs(x) >= 10 else f"{'−' if x < 0 else '+'}${abs(x):,.2f}{unit}"
