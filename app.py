"""Fed Decoder: Federal Reserve decisions in plain English. Streamlit app."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from fed_decoder import config
from fed_decoder.analysis import forecast as forecast_mod
from fed_decoder.analysis import tone as tone_mod
from fed_decoder.cards.builder import build_llm_card
from fed_decoder.cards.context import build_context, build_context_pasted
from fed_decoder.cards.rules import RULES_LABEL, build_rules_card
from fed_decoder.cards.store import all_cards, load_card
from fed_decoder.chat import agent
from fed_decoder.data import store
from fed_decoder.ui import components as ui
from fed_decoder.ui.theme import CSS

st.set_page_config(page_title="Fed Decoder", page_icon=None, layout="centered", initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)

PAGES = ["Decode", "Ask", "Timeline"]
ss = st.session_state
ss.setdefault("nav", "Decode")
ss.setdefault("nav_v", 0)
ss.setdefault("meeting", None)
ss.setdefault("questions", 0)
ss.setdefault("chat", [])


@st.cache_data(show_spinner=False)
def meetings() -> pd.DataFrame:
    return store.ground_truth()[["meeting_date", "direction", "change_bps", "target_low", "target_high"]].copy()


@st.cache_data(show_spinner=False)
def tones() -> dict[str, float]:
    return {d: c.tone_score for d, c in all_cards().items()}


@st.cache_data(show_spinner=False, ttl=3600)
def cached_forecast() -> dict:
    return forecast_mod.forecast_next().to_dict()


@st.cache_data(show_spinner=False)
def cached_context(date_str: str) -> dict:
    return build_context(date_str)


def go(page: str, meeting: str | None = None) -> None:
    ss.nav = page
    ss.nav_v += 1
    if meeting:
        ss.meeting = meeting


def label_for(row) -> str:
    move = {"hike": f"raised {abs(row.change_bps)} bp", "cut": f"cut {abs(row.change_bps)} bp", "hold": "held"}[row.direction]
    return f"{row.meeting_date:%B %-d, %Y} · {move}"


# ---- header & nav ------------------------------------------------------------
st.markdown('<div class="kicker">Federal Reserve, in plain English</div>', unsafe_allow_html=True)
st.markdown("<h1>Fed Decoder</h1>", unsafe_allow_html=True)
choice = st.radio("Section", PAGES, index=PAGES.index(ss.nav), horizontal=True, label_visibility="collapsed", key=f"nav_{ss.nav_v}")
if choice != ss.nav:
    ss.nav = choice
st.markdown('<hr class="rule">', unsafe_allow_html=True)


def provider_line(card) -> str:
    if card.provider == "rules":
        return RULES_LABEL
    return {"gemini": "Card written by Gemini Flash", "groq": "Card written by Groq (open-weight model)"}.get(card.provider, card.provider) + " · numbers computed in code"


def for_you_items(card, ctx) -> list[dict]:
    facts = {b["topic"]: b for b in ctx["impacts"]["for_you"]}
    items = []
    for topic in ("Borrowers", "Mortgages", "Savers", "Workers"):
        f = facts.get(topic)
        if not f:
            continue
        llm = next((b.text for b in card.for_you if b.topic.lower() == topic.lower()), None)
        text = llm if (llm and card.provider != "rules") else f["text"]
        if topic == "Mortgages" and "10-year" not in text:
            text = "Mortgages track the 10-year Treasury yield, not the fed funds rate. " + text
        items.append({"topic": topic, "number": f["number"], "text": text})
    return items


def render_card(card, ctx, is_latest: bool) -> None:
    d = card.decision
    when = "Pasted statement" if ctx["meeting_date"] == "pasted" else f"{pd.Timestamp(ctx['meeting_date']):%B %-d, %Y}"
    st.markdown(f'<div class="kicker">{when}</div>', unsafe_allow_html=True)
    st.markdown(f"<h2>{ui.E(d.summary.split('. The vote')[0].rstrip('.'))}.</h2>", unsafe_allow_html=True)
    st.markdown(ui.facts_html(d, ctx["meeting_date"]), unsafe_allow_html=True)
    st.markdown(f'<div class="prov" style="margin-top:8px">{ui.E(provider_line(card))}</div>', unsafe_allow_html=True)

    # What changed
    st.markdown("<h3>What changed</h3>", unsafe_allow_html=True)
    if ctx.get("prev_statement"):
        ref = ctx["prev_meeting_date"]
        extra = f" (most similar past statement, similarity {ctx['similarity']:.2f})" if ctx["meeting_date"] == "pasted" else ""
        pct = round((ctx.get("changed_fraction") or 0) * 100)
        st.markdown(f'<div class="small">Compared with {ref}{extra}. {pct}% of words changed. '
                    'Struck text was removed, highlighted text was added; hover a change for what it means.</div>', unsafe_allow_html=True)
    st.markdown(ui.redline_html(ctx.get("prev_statement"), ctx["statement"], card.changes), unsafe_allow_html=True)

    # Tone
    st.markdown('<hr class="rule"><h3>Tone</h3>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1.25])
    with c1:
        st.markdown(ui.tone_dial_svg(card.tone_score), unsafe_allow_html=True)
        tr = tone_mod.score(ctx["statement"])
        st.markdown(f'<div class="small">Scale −2 (dovish) to +2 (hawkish). Dictionary model: <span class="mono">{tr.score:+.1f}</span>.</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="small">The lines that drive it</div>', unsafe_allow_html=True)
        st.markdown(ui.quotes_html(card.tone_quotes[:3]), unsafe_allow_html=True)

    # For you
    st.markdown('<hr class="rule"><h3>For you</h3>', unsafe_allow_html=True)
    st.markdown(ui.cards_html(for_you_items(card, ctx)), unsafe_allow_html=True)
    st.markdown('<div class="small" style="margin-top:8px">Example balances: $5,000 card, $300,000 30-year mortgage, $10,000 savings. Amortization computed in code.</div>', unsafe_allow_html=True)

    # For the country
    st.markdown('<hr class="rule"><h3>For the country</h3>', unsafe_allow_html=True)
    facts = {b["topic"]: b for b in ctx["impacts"]["for_country"]}
    rows = []
    for topic, f in facts.items():
        llm = next((b.text for b in card.for_country if b.topic.lower() == topic.lower()), None)
        rows.append({"topic": topic, "number": f["number"], "text": llm if (llm and card.provider != "rules") else f["text"]})
    st.markdown(ui.cards_html(rows), unsafe_allow_html=True)

    # What's next
    st.markdown("<hr class=\"rule\"><h3>What's next</h3>", unsafe_allow_html=True)
    st.markdown(f"<p>{ui.E(card.whats_next)}</p>", unsafe_allow_html=True)
    if is_latest:
        f = cached_forecast()
        bt = f["backtest"]
        st.markdown(f'<div class="kicker">Model forecast for the next meeting · {f["confidence"]} confidence</div>', unsafe_allow_html=True)
        st.markdown(ui.prob_bars({"hold": f["p_hold"], "cut": f["p_cut"], "hike": f["p_hike"]}), unsafe_allow_html=True)
        s = f["signals"]
        st.markdown(
            f'<div class="small">Signals: Taylor rule <span class="mono">{s["taylor_rate"]:.2f}%</span> vs current midpoint '
            f'<span class="mono">{s["current_mid"]:.3f}%</span>; SEP median <span class="mono">{s["sep_median"] if s["sep_median"] is not None else "n/a"}%</span>; '
            f'tone trend <span class="mono">{s["tone_trend"]:+.2f}</span>.</div>', unsafe_allow_html=True)
        verdict = ("beats" if bt.get("beats_baseline") else "does not beat")
        st.markdown(
            f'<div class="small">Backtest {bt.get("start")} to {bt.get("end")} ({bt.get("n")} meetings): model hit rate '
            f'<span class="mono">{bt.get("model_hit_rate", 0) * 100:.0f}%</span> vs “no change” baseline '
            f'<span class="mono">{bt.get("baseline_hit_rate", 0) * 100:.0f}%</span>. The model {verdict} the baseline. '
            'Educational, not financial advice.</div>', unsafe_allow_html=True)
    elif ctx.get("forecast"):
        fc = ctx["forecast"]
        st.markdown('<div class="kicker">What the model said at the time about the next meeting</div>', unsafe_allow_html=True)
        st.markdown(ui.prob_bars({k: fc[k] / 100 for k in ("hold", "cut", "hike")}), unsafe_allow_html=True)
        st.markdown('<div class="small">Walk-forward backtest: trained only on earlier meetings. Educational, not financial advice.</div>', unsafe_allow_html=True)

    with st.expander("Full statement and sources"):
        st.markdown(f'<div class="redline">{"".join(f"<p>{ui.E(p)}</p>" for p in ctx["statement"].split(chr(10) + chr(10)))}</div>', unsafe_allow_html=True)
        for c in card.citations:
            st.markdown(f'<div class="small"><span class="mono">{ui.E(c.source)}</span> · {ui.E(c.detail)}</div>', unsafe_allow_html=True)


def page_decode() -> None:
    m = meetings().sort_values("meeting_date", ascending=False).reset_index(drop=True)
    labels = [label_for(r) for r in m.itertuples()]
    dates = [r.meeting_date.strftime("%Y-%m-%d") for r in m.itertuples()]
    mode = st.radio("Source", ["Pick a meeting", "Paste a statement"], horizontal=True, label_visibility="collapsed")
    if mode == "Pick a meeting":
        idx = dates.index(ss.meeting) if ss.meeting in dates else 0
        sel = st.selectbox("FOMC meeting", range(len(labels)), index=idx, format_func=lambda i: labels[i])
        ss.meeting = dates[sel]
        ctx = cached_context(ss.meeting)
        card = load_card(ss.meeting) or build_rules_card(ctx)
        render_card(card, ctx, is_latest=(sel == 0))
    else:
        st.markdown(f'<div class="small">{ui.E(config.PRIVACY_NOTICE)} Pasted text is treated as data, never as instructions.</div>', unsafe_allow_html=True)
        text = st.text_area("Paste an FOMC statement", height=220, max_chars=8000, label_visibility="collapsed",
                            placeholder="Paste the text of an FOMC statement here…")
        if st.button("Decode") and text.strip():
            ss.pasted = text
        if ss.get("pasted"):
            ctx = build_context_pasted(ss.pasted)
            card = None
            if not agent.near_cap():
                with st.spinner("Decoding…"):
                    try:
                        agent._bump_daily()
                        card = build_llm_card(ctx)
                    except Exception:
                        card = None
            if card is None:
                card = build_rules_card(ctx)
            render_card(card, ctx, is_latest=False)


def page_ask() -> None:
    st.markdown("<h2>Ask about the Fed</h2>", unsafe_allow_html=True)
    st.markdown(f'<div class="small">{ui.E(config.PRIVACY_NOTICE)} Answers use tools over the statements and FRED data; '
                f'every number is checked against the tool results. {config.SESSION_QUESTION_LIMIT} questions per session.</div>', unsafe_allow_html=True)
    examples = ["Why did the Fed cut in September 2024?", "What does a 25 bp hike mean for my mortgage?", "What will the Fed do at the next meeting?"]
    cols = st.columns(len(examples))
    pending = None
    for c, q in zip(cols, examples):
        if c.button(q, use_container_width=True):
            pending = q
    for msg in ss.chat:
        with st.chat_message(msg["role"], avatar=None):
            st.markdown(msg["content"])
            if msg.get("label"):
                st.markdown(f'<div class="prov">{ui.E(msg["label"])}</div>', unsafe_allow_html=True)
    left = config.SESSION_QUESTION_LIMIT - ss.questions
    q = st.chat_input("Ask a question about Fed decisions" if left > 0 else "Question limit reached for this session", disabled=left <= 0)
    q = q or pending
    if q and left > 0:
        ss.questions += 1
        with st.chat_message("user", avatar=None):
            st.markdown(q)
        hist = [{"role": m["role"], "content": m["content"]} for m in ss.chat][-2 * config.CHAT_HISTORY_TURNS:]
        with st.chat_message("assistant", avatar=None):
            with st.spinner("Looking it up…"):
                try:
                    ans = agent.answer(q, history=hist)
                except Exception:
                    ans = agent.rules_answer(q)
            st.markdown(ans.text)
            label = ans.label + (" · cached" if ans.cached else "")
            st.markdown(f'<div class="prov">{ui.E(label)}</div>', unsafe_allow_html=True)
        ss.chat += [{"role": "user", "content": q}, {"role": "assistant", "content": ans.text, "label": label}]


def page_timeline() -> None:
    st.markdown("<h2>Every decision since 2000</h2>", unsafe_allow_html=True)
    st.markdown('<div class="small">The line is the fed funds target (range shaded since December 2008). Each dot is a meeting, '
                'colored by the tone of its statement. Click a dot to decode that meeting.</div>', unsafe_allow_html=True)
    fig = ui.timeline_fig(meetings(), tones())
    ev = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points", key="timeline",
                         config={"displayModeBar": False})
    pts = (ev or {}).get("selection", {}).get("points", []) if isinstance(ev, dict) else getattr(getattr(ev, "selection", None), "points", [])
    if pts:
        p = pts[0]
        date = p.get("customdata")
        if isinstance(date, list):
            date = date[0]
        if date:
            go("Decode", str(date)[:10])
            st.rerun()
    with st.expander("Table view"):
        t = meetings().copy()
        t["tone"] = t["meeting_date"].dt.strftime("%Y-%m-%d").map(tones())
        t["meeting_date"] = t["meeting_date"].dt.date
        st.dataframe(t.sort_values("meeting_date", ascending=False), hide_index=True, use_container_width=True)


{"Decode": page_decode, "Ask": page_ask, "Timeline": page_timeline}[ss.nav]()
st.markdown(ui.footer_html(config.FOOTER), unsafe_allow_html=True)
