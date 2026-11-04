"""Fed Decoder: Federal Reserve decisions in plain English. Streamlit app.

Presentation only. Every number shown comes from the data and calculation
layers (fed_decoder.data / analysis / cards); explanations come from the
validated decoder cards. Personal calculator inputs never leave this session.
"""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from fed_decoder import config
from fed_decoder.analysis import forecast as forecast_mod
from fed_decoder.analysis import personal
from fed_decoder.analysis import tone as tone_mod
from fed_decoder.cards.builder import build_llm_card
from fed_decoder.cards.context import build_context, build_context_pasted
from fed_decoder.cards.rules import RULES_LABEL, build_rules_card
from fed_decoder.cards.store import all_cards, load_card
from fed_decoder.chat import agent
from fed_decoder.chat.tools import parse_date, resolve_meeting
from fed_decoder.data import store
from fed_decoder.ui import components as ui
from fed_decoder.ui.theme import CSS

st.set_page_config(page_title="Fed Decoder", page_icon=None, layout="centered", initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)

PAGES = ["Decode", "Timeline", "Ask", "About"]
STEPS = ["decision", "changed", "tone", "you", "economy", "next"]
NEXT_LABEL = {
    "changed": "Continue: what changed in the statement",
    "tone": "Continue: how the Fed sounded",
    "you": "Continue: what it means for you",
    "economy": "Continue: what it means for the economy",
    "next": "Continue: what might happen next",
}
ss = st.session_state
ss.setdefault("nav", "Decode")
ss.setdefault("nav_v", 0)
ss.setdefault("meeting", None)       # "YYYY-MM-DD", "pasted", or None (home)
ss.setdefault("step", 0)
ss.setdefault("questions", 0)
ss.setdefault("chat", [])


# ---------------------------------------------------------------- cached data
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


def dates() -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in meetings()["meeting_date"]]


def go(page: str, meeting: str | None = None) -> None:
    ss.nav = page
    ss.nav_v += 1
    if meeting:
        open_meeting(meeting)


def open_meeting(m: str | None) -> None:
    ss.meeting = m
    ss.step = 0


def long_date(d: str) -> str:
    return f"{pd.Timestamp(d):%B %-d, %Y}"


# ---------------------------------------------------------------- top bar
top_l, top_r = st.columns([1, 2.2], vertical_alignment="center")
with top_l:
    st.markdown('<div class="wordmark">Fed <span>Decoder</span></div>', unsafe_allow_html=True)
with top_r:
    with st.container(key="nav"):
        choice = st.radio("Go to", PAGES, index=PAGES.index(ss.nav), horizontal=True, label_visibility="collapsed", key=f"nav_{ss.nav_v}")
if choice != ss.nav:
    ss.nav = choice
    st.rerun()


# ---------------------------------------------------------------- home: start from what the user enters
def interpret(text: str) -> tuple[str | None, str | None]:
    """Turn what someone typed into a meeting date, 'pasted', or an error message."""
    t = text.strip()
    if not t:
        return None, None
    all_dates = dates()
    if len(t) > 280 and re.search(r"\b(Committee|federal funds|FOMC)\b", t, re.I):
        return "pasted", None
    tl = t.lower()
    if re.search(r"\b(latest|last meeting|most recent|recent|newest|this week|today|now)\b", tl):
        return all_dates[-1], None
    m = re.search(r"\blast (january|february|march|april|may|june|july|august|september|october|november|december)\b", tl)
    if m:
        latest = pd.Timestamp(all_dates[-1])
        month = pd.Timestamp(f"1 {m.group(1)} 2000").month
        year = latest.year if month <= latest.month else latest.year - 1
        t = f"{m.group(1)} {year}"
    when = parse_date(t)
    if when is None:
        return None, "I couldn't tell which meeting you mean. Try a month and year, such as “September 2024”, or type “latest”."
    if when < pd.Timestamp("2000-01-01"):
        return None, "Fed Decoder covers meetings from February 2000 onward."
    if when > pd.Timestamp(all_dates[-1]) + pd.Timedelta(days=45):
        return None, f"There's no statement after {long_date(all_dates[-1])} yet."
    d = resolve_meeting(t)
    return (str(d.date()) if d is not None else None), None


def page_home() -> None:
    st.markdown('<div style="height:7vh"></div>', unsafe_allow_html=True)
    st.markdown("<h1>Which Fed decision do you want to understand?</h1>", unsafe_allow_html=True)
    st.markdown('<p class="lede">Type a month, a date or “latest”. You can also paste the text of a Fed statement.</p>', unsafe_allow_html=True)
    with st.form("ask_meeting", border=False):
        text = st.text_area("Meeting or statement", label_visibility="collapsed", height=90, max_chars=8000,
                            placeholder="For example: latest, September 2024, or March 2020")
        c1, c2 = st.columns([1, 3], vertical_alignment="center")
        submitted = c1.form_submit_button("Decode it", type="primary", use_container_width=True)
        c2.markdown('<div class="note">Don’t enter personal information. Pasted text is treated as data, never as instructions.</div>',
                    unsafe_allow_html=True)
    if submitted:
        target, err = interpret(text)
        if err:
            st.markdown(f'<p class="muted">{ui.E(err)}</p>', unsafe_allow_html=True)
        elif target == "pasted":
            ss.pasted = text
            open_meeting("pasted")
            st.rerun()
        elif target:
            open_meeting(target)
            st.rerun()
    st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)
    c1, c2, _ = st.columns([1, 1.25, 1.2])
    if c1.button(f"The latest meeting, {pd.Timestamp(dates()[-1]):%b %-d}", type="tertiary"):
        open_meeting(dates()[-1])
        st.rerun()
    if c2.button("Browse all meetings since 2000", type="tertiary"):
        go("Timeline")
        st.rerun()


# ---------------------------------------------------------------- decoder sections
def provider_note(card) -> str:
    if card.provider == "rules":
        return f"{RULES_LABEL}. Numbers are computed from Federal Reserve and FRED data."
    who = {"gemini": "Gemini", "groq": "Groq"}.get(card.provider, card.provider)
    return f"Explanation written by {who} and checked against the statement; every number comes from Federal Reserve and FRED data."


def for_you_items(card, ctx) -> list[dict]:
    facts = {b["topic"]: b for b in ctx["impacts"]["for_you"]}
    items = []
    for topic, label in (("Borrowers", "Credit cards"), ("Mortgages", "Mortgages"), ("Savers", "Savings"), ("Workers", "Jobs")):
        f = facts.get(topic)
        if not f:
            continue
        llm = next((b.text for b in card.for_you if b.topic.lower() == topic.lower()), None)
        text = llm if (llm and card.provider != "rules") else f["text"]
        if topic == "Mortgages" and "10-year" not in text:
            text = "Mortgages track the 10-year Treasury yield, not the fed funds rate. " + text
        items.append({"topic": label, "number": f["number"], "text": text})
    return items


def section_decision(card, ctx) -> None:
    d = card.decision
    when = "Your pasted statement" if ctx["meeting_date"] == "pasted" else long_date(ctx["meeting_date"])
    st.markdown(f'<div class="step first"><div class="dateline">{when}</div>'
                f'<h1>{ui.E(ui.headline(d.direction, d.change_bps))}</h1>{ui.facts_html(d)}</div>', unsafe_allow_html=True)
    if d.direction == "hold":
        p1 = f"The FOMC left the federal funds rate where it was, with the target range at {ui.fmt_range(d.target_low, d.target_high)}."
    else:
        p1 = (f"The FOMC {'lowered' if d.direction == 'cut' else 'raised'} the federal funds rate by {abs(d.change_bps)} basis points, "
              f"which moves the target range to {ui.fmt_range(d.target_low, d.target_high)}.")
    p1 += " " + ui.vote_sentence(d) if ui.vote_sentence(d) else ""
    body = f"<p>{ui.define(ui.E(p1), ['FOMC', 'federal funds rate', 'basis points', 'target range', 'dissented'])}</p>"
    if card.tone_quotes:
        body += f'<div class="say">“{ui.E(card.tone_quotes[0].quote)}”</div>'
    st.markdown(f'<div class="prose">{body}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="aside"><div class="aside-h">Why it matters</div><p>{ui.define(ui.E(ui.why_it_matters(d.direction)), ["10-year Treasury"])}</p></div>',
                unsafe_allow_html=True)


def section_changed(card, ctx) -> None:
    st.markdown('<div class="step"><h2>What changed in the statement</h2></div>', unsafe_allow_html=True)
    if not ctx.get("prev_statement"):
        st.markdown('<p class="muted">This is the first statement in the record, so there is nothing to compare it with.</p>', unsafe_allow_html=True)
        return
    ref = "the most similar past statement, from " + long_date(ctx["prev_meeting_date"]) if ctx["meeting_date"] == "pasted" else "the previous statement, from " + long_date(ctx["prev_meeting_date"])
    pct = round((ctx.get("changed_fraction") or 0) * 100)
    st.markdown(f'<div class="prose"><p>Compared with {ref}, about {pct}% of the wording changed. Fed statements are edited word by word, '
                'so even small changes are deliberate. <del class="key">Struck</del> words were removed, <ins class="key">shaded</ins> ones added, '
                'and the numbers point to what each change means.</p></div>', unsafe_allow_html=True)
    red, notes = ui.redline_html(ctx.get("prev_statement"), ctx["statement"], card.changes)
    st.markdown(f'<div class="margin-notes">{red}{ui.notes_html(notes)}</div>', unsafe_allow_html=True)


def section_tone(card, ctx) -> None:
    st.markdown('<div class="step"><h2>How the Fed sounded</h2></div>', unsafe_allow_html=True)
    st.markdown('<div class="prose"><p>Beyond the decision itself, the wording signals which way the Fed is leaning. '
                + ui.define("Hawkish", ["hawkish"]) + " language points toward higher rates; " + ui.define("dovish", ["dovish"])
                + " language points toward lower ones.</p></div>", unsafe_allow_html=True)
    st.markdown(ui.tone_scale_html(card.tone_score), unsafe_allow_html=True)
    if card.tone_quotes:
        st.markdown(ui.quotes_html(card.tone_quotes[:3]), unsafe_allow_html=True)
    with st.expander("How the tone score works"):
        tr = tone_mod.score(ctx["statement"])
        st.markdown(f'<p class="note">The score comes from the decoder card, which reads the whole statement. As a cross-check, a simple word-list model '
                    f'scores this statement <span class="fig">{tr.score:+.1f}</span>. The two agree on direction most of the time, and the card score '
                    'predicts the next rate move better.</p>', unsafe_allow_html=True)


def personal_calculator(ctx, change_bps: int) -> None:
    """Optional, one question at a time. Answers live only in this browser session;
    they are never stored, logged, cached or sent to an AI provider."""
    with st.container(key="calc"):
        st.markdown('<h3>Work out your own numbers</h3><p class="note" style="margin:0">Optional. Your answers stay in this browser tab: '
                    'nothing is saved or sent to an AI, and there’s no login.</p>', unsafe_allow_html=True)
        st.markdown('<div class="qa">Where do you live?</div>', unsafe_allow_html=True)
        with st.container(key="tiles_housing"):
            housing = st.radio("Housing", list(personal.HOUSING), index=None, format_func=personal.HOUSING.get,
                               label_visibility="collapsed", key="p_housing")
        if housing is None:
            return
        mort = 0.0
        if housing in ("arm", "buying"):
            mort = st.number_input("How much is the mortgage?" if housing == "arm" else "How much do you plan to borrow?",
                                   min_value=0, step=10_000, value=None, placeholder="For example 300000", key="p_mort") or 0.0

        st.markdown('<div class="qa">Do you have any of these?</div><div class="qa-sub">Pick any that apply.</div>', unsafe_allow_html=True)
        with st.container(key="checks"):
            c1, c2 = st.columns(2)
            has_card = c1.checkbox("A credit card balance I carry", key="p_has_card")
            has_heloc = c2.checkbox("A home equity line", key="p_has_heloc")
            has_stud = c1.checkbox("A variable-rate private student loan", key="p_has_stud")
            shopping_car = c2.checkbox("I'm shopping for a car loan", key="p_car_shop")
            has_car = c1.checkbox("A fixed-rate car loan", key="p_car_fixed")
        car = "shopping" if shopping_car else "have_fixed" if has_car else "none"
        amounts = {}
        cols = st.columns(2)
        slot = 0
        for flag, key, label in ((has_card, "card", "Card balance you carry"), (has_heloc, "heloc", "Home equity balance"),
                                 (has_stud, "stud", "Private student loan balance"), (car == "shopping", "car", "Car loan amount")):
            if flag:
                amounts[key] = cols[slot % 2].number_input(label, min_value=0, step=500, value=None, placeholder="Amount in dollars", key=f"p_{key}") or 0.0
                slot += 1

        st.markdown('<div class="qa">Do you have savings?</div>', unsafe_allow_html=True)
        with st.container(key="tiles_savings"):
            sav_kind = st.radio("Savings", ["none", "high_yield", "bank"], index=None, label_visibility="collapsed", key="p_sav_kind",
                                format_func={"none": "Not really", "high_yield": "Yes, high-yield or money market", "bank": "Yes, a regular bank account"}.get)
        sav = 0.0
        if sav_kind in ("high_yield", "bank"):
            sav = st.number_input("About how much?", min_value=0, step=1_000, value=None, placeholder="Amount in dollars", key="p_sav") or 0.0

        with st.expander("Put it in context (optional)"):
            c1, c2 = st.columns(2)
            income = c1.selectbox("Household income", list(personal.INCOME), key="p_income")
            states = [None] + list(config.STATES)
            state = c2.selectbox("State, for local jobs data", states, key="p_state",
                                 format_func=lambda k: "Prefer not to say" if k is None else config.STATES[k])

        prof = personal.Profile(housing=housing, mortgage_balance=float(mort), heloc_balance=float(amounts.get("heloc", 0)),
                                card_balance=float(amounts.get("card", 0)), car_loan=car, car_amount=float(amounts.get("car", 0)),
                                private_student_variable=float(amounts.get("stud", 0)), savings=float(sav),
                                savings_kind=sav_kind if sav_kind in personal.SAVINGS_KIND else "bank", income=income, state=state)
        ten = ((ctx["impacts"].get("numbers") or {}).get("mortgage_30y") or {}).get("rate_change_bps")
        when = pd.Timestamp.today() if ctx["meeting_date"] == "pasted" else ctx["meeting_date"]
        r = personal.personal_impact(prof, change_bps, ten, when)
        render_personal_result(r, change_bps)
        if st.button("Clear my answers", type="tertiary"):
            for k in [k for k in ss.keys() if str(k).startswith("p_")]:
                del ss[k]
            st.rerun()


def render_personal_result(r, change_bps: int) -> None:
    affected = [i for i in r.items if abs(i.get("monthly", 0)) >= 0.005]
    unaffected = [i for i in r.items if abs(i.get("monthly", 0)) < 0.005 and i["topic"] != "Jobs where you live"]
    local = [i for i in r.items if i["topic"] == "Jobs where you live"]
    total = r.monthly_total
    if change_bps == 0 or not affected:
        big = "No change"
        expl = "This decision didn’t change anything you pay or earn that follows the Fed."
    else:
        big = f"{'−' if total < 0 else '+'}${abs(total):,.2f} a month"
        expl = f"{'Less' if total < 0 else 'More'} going out each month across the products below"
        expl += f", about {abs(r.share_of_income):.2f}% of your monthly income." if r.share_of_income is not None else "."
    html = f'<div class="result reveal"><div class="muted" style="font-size:15px">Your estimated monthly impact</div><div class="big">{ui.E(big)}</div><p style="margin:0">{ui.E(expl)}</p>'
    if affected:
        html += "<h4>Changes with this decision</h4>" + ui.rows_html(affected)
    if unaffected:
        html += "<h4>Doesn’t change</h4>" + ui.rows_html(unaffected)
    if local:
        html += "<h4>Where you live</h4>" + ui.rows_html(local)
    if r.per_25bp_monthly:
        html += (f'<p class="note" style="margin-top:14px">Rule of thumb for you: every quarter-point Fed move shifts your monthly costs by about '
                 f'<span class="tab">${abs(r.per_25bp_monthly):,.2f}</span>.</p>')
    html += '<p class="note" style="margin-top:6px">Estimates use national average rates, not your actual loan terms. Not financial advice.</p></div>'
    st.markdown(html, unsafe_allow_html=True)


def section_you(card, ctx) -> None:
    st.markdown('<div class="step"><h2>What it means for you</h2></div>', unsafe_allow_html=True)
    st.markdown('<div class="prose"><p>For a typical household, using example balances: a $5,000 credit card balance, '
                'a $300,000 mortgage and $10,000 in savings.</p></div>', unsafe_allow_html=True)
    st.markdown(ui.rows_html(for_you_items(card, ctx)), unsafe_allow_html=True)
    personal_calculator(ctx, card.decision.change_bps)


def section_economy(card, ctx) -> None:
    st.markdown('<div class="step"><h2>What it means for the economy</h2></div>', unsafe_allow_html=True)
    st.markdown('<div class="prose"><p>The Fed’s two jobs are stable prices and maximum employment. Here is where things stood, '
                'using the data that was public at the time.</p></div>', unsafe_allow_html=True)
    rows = []
    for b in ctx["impacts"]["for_country"]:
        llm = next((x.text for x in card.for_country if x.topic.lower() == b["topic"].lower()), None)
        rows.append({"topic": b["topic"], "number": b["number"], "text": llm if (llm and card.provider != "rules") else b["text"]})
    st.markdown(ui.briefing_html(rows), unsafe_allow_html=True)


def section_next(card, ctx, is_latest: bool) -> None:
    st.markdown("<div class=\"step\"><h2>What might happen next</h2></div>", unsafe_allow_html=True)
    st.markdown(f'<div class="prose"><p>{ui.E(card.whats_next)}</p></div>', unsafe_allow_html=True)
    if is_latest:
        f = cached_forecast()
        bt = f["backtest"]
        st.markdown(f'<h3 class="gap">Our model’s odds for the next meeting</h3>'
                    f'{ui.odds_html({"hold": f["p_hold"], "cut": f["p_cut"], "hike": f["p_hike"]})}', unsafe_allow_html=True)
        verdict = "better than" if bt.get("beats_baseline") else "no better than"
        st.markdown(f'<p class="note">Confidence: {f["confidence"]}. Tested on {bt.get("n")} past meetings, the model was right '
                    f'{bt.get("model_hit_rate", 0) * 100:.0f}% of the time, {verdict} simply guessing “no change” '
                    f'({bt.get("baseline_hit_rate", 0) * 100:.0f}%). Educational, not financial advice.</p>', unsafe_allow_html=True)
        with st.expander("What goes into the forecast"):
            s = f["signals"]
            sep = f'{s["sep_median"]:.2f}%' if s["sep_median"] is not None else "not available"
            st.markdown(f'<p class="note">A rule of thumb called the Taylor rule, using inflation and how hot the economy is running, suggests a rate of '
                        f'<span class="fig">{s["taylor_rate"]:.2f}%</span>, against a current midpoint of <span class="fig">{s["current_mid"]:.3f}%</span>. '
                        f'Fed officials’ own median projection is {sep}. The model also weighs the tone of recent statements and the last rate move.</p>',
                        unsafe_allow_html=True)
    elif ctx.get("forecast") and ctx["meeting_date"] != "pasted":
        fc = ctx["forecast"]
        st.markdown('<h3 class="gap">What our model expected at the time</h3>'
                    + ui.odds_html({k: fc[k] / 100 for k in ("hold", "cut", "hike")}), unsafe_allow_html=True)
        all_d = dates()
        i = all_d.index(ctx["meeting_date"])
        if i + 1 < len(all_d):
            nxt = all_d[i + 1]
            g = meetings().set_index(meetings()["meeting_date"].dt.strftime("%Y-%m-%d")).loc[nxt]
            st.markdown(f'<p>What actually happened next: on {long_date(nxt)}, {ui.headline(g["direction"], int(g["change_bps"]))[0].lower()}'
                        f'{ui.headline(g["direction"], int(g["change_bps"]))[1:]}.</p>', unsafe_allow_html=True)
        st.markdown('<p class="note">The model only used information available at the time. Educational, not financial advice.</p>', unsafe_allow_html=True)


def sources(card, ctx) -> None:
    with st.expander("Sources and the full statement"):
        st.markdown(f'<p class="note">{ui.E(provider_note(card))}</p>', unsafe_allow_html=True)
        st.markdown('<div class="redline">' + "".join(f"<p>{ui.E(p)}</p>" for p in ctx["statement"].split("\n\n")) + "</div>", unsafe_allow_html=True)
        cites = "".join(f'<li><span class="fig">{ui.E(c.source)}</span>: {ui.E(c.detail)}</li>' for c in card.citations if c.source != "statement")
        if cites:
            st.markdown(f'<p class="note" style="margin-top:8px">Data used</p><ul class="note">{cites}</ul>', unsafe_allow_html=True)


def decoder(card, ctx, is_latest: bool) -> None:
    show_all = ss.get("show_all", False)
    last = len(STEPS) - 1 if show_all else min(ss.step, len(STEPS) - 1)
    renders = {"decision": lambda: section_decision(card, ctx), "changed": lambda: section_changed(card, ctx),
               "tone": lambda: section_tone(card, ctx), "you": lambda: section_you(card, ctx),
               "economy": lambda: section_economy(card, ctx), "next": lambda: section_next(card, ctx, is_latest)}
    for i, key in enumerate(STEPS[: last + 1]):
        renders[key]()
    st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)
    if last < len(STEPS) - 1:
        c1, c2 = st.columns([0.62, 1], vertical_alignment="center", gap="small")
        if c1.button(NEXT_LABEL[STEPS[last + 1]], type="primary", key=f"cont_{last}", use_container_width=True):
            ss.step = last + 1
            st.rerun()
        if c2.button("or show the whole explanation", type="tertiary"):
            ss.show_all = True
            st.rerun()
    else:
        sources(card, ctx)
        if ctx["meeting_date"] != "pasted":
            all_d = dates()
            i = all_d.index(ctx["meeting_date"])
            with st.container(key="pager"):
                c1, c2 = st.columns(2)
                if i > 0 and c1.button(f"← {long_date(all_d[i - 1])}", type="tertiary", key="pg_prev"):
                    open_meeting(all_d[i - 1]); st.rerun()
                if i + 1 < len(all_d) and c2.button(f"{long_date(all_d[i + 1])} →", type="tertiary", key="pg_next"):
                    open_meeting(all_d[i + 1]); st.rerun()


def page_decode() -> None:
    if not ss.meeting:
        page_home()
        return
    if st.button("← Choose another meeting", type="tertiary", key="restart_top"):
        open_meeting(None)
        st.rerun()
    if ss.meeting == "pasted":
        ctx = build_context_pasted(ss.get("pasted", ""))
        card = ss.get("pasted_card")
        if card is None or ss.get("pasted_card_for") != ss.get("pasted"):
            card = None
            if not agent.near_cap():
                with st.spinner("Reading the statement…"):
                    try:
                        agent._bump_daily()
                        card = build_llm_card(ctx)
                    except Exception:
                        card = None
            card = card or build_rules_card(ctx)
            ss.pasted_card, ss.pasted_card_for = card, ss.get("pasted")
        decoder(card, ctx, is_latest=False)
        return
    ctx = cached_context(ss.meeting)
    card = load_card(ss.meeting) or build_rules_card(ctx)
    decoder(card, ctx, is_latest=(ss.meeting == dates()[-1]))


# ---------------------------------------------------------------- timeline
def page_timeline() -> None:
    st.markdown('<div class="step" style="padding-top:28px"><h1>Every Fed decision since 2000</h1></div>', unsafe_allow_html=True)
    st.markdown('<p class="lede">The line is the Fed’s interest rate target. Each dot is a meeting; the larger dots are rate changes. '
                f'Color shows the tone of the statement, from <span class="dove">dovish</span> to <span class="hawk">hawkish</span>. '
                'Tap or click a dot to see that meeting.</p>', unsafe_allow_html=True)
    fig = ui.timeline_fig(meetings(), tones(), selected=ss.get("tl_pick"))
    ev = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points", key="timeline",
                         config={"displayModeBar": False, "scrollZoom": False})
    pts = (ev or {}).get("selection", {}).get("points", []) if isinstance(ev, dict) else getattr(getattr(ev, "selection", None), "points", [])
    for p in pts:
        cd = p.get("customdata")
        if isinstance(cd, list):
            cd = cd[0]
        if cd and re.match(r"\d{4}-\d{2}-\d{2}", str(cd)):
            ss.tl_pick = str(cd)[:10]
            break
    pick = ss.get("tl_pick")
    if pick:
        g = meetings().set_index(meetings()["meeting_date"].dt.strftime("%Y-%m-%d")).loc[pick]
        word, cls = ui.tone_words(tones().get(pick, 0.0))
        with st.container(key="picked"):
            st.markdown(f'<div class="reveal"><div class="muted" style="font-size:15px">{long_date(pick)}</div>'
                        f'<h2 style="margin-top:4px">{ui.E(ui.headline(g["direction"], int(g["change_bps"])))}</h2>'
                        f'<p style="margin:0">Target range {ui.fmt_range(g["target_low"], g["target_high"])}. '
                        f'Tone: <strong class="{cls}">{word.lower()}</strong>.</p></div>', unsafe_allow_html=True)
            if st.button("Walk through this meeting", type="primary"):
                go("Decode", pick)
                st.rerun()
    with st.expander("See the meetings as a table"):
        t = meetings().copy()
        t["tone"] = t["meeting_date"].dt.strftime("%Y-%m-%d").map(tones()).round(1)
        t = t.rename(columns={"meeting_date": "Meeting", "direction": "Decision", "change_bps": "Change (bp)",
                              "target_low": "Range low (%)", "target_high": "Range high (%)", "tone": "Tone (−2 to +2)"})
        t["Meeting"] = t["Meeting"].dt.date
        st.dataframe(t.sort_values("Meeting", ascending=False), hide_index=True, use_container_width=True)


# ---------------------------------------------------------------- ask
def page_ask() -> None:
    st.markdown('<div class="step" style="padding-top:28px"><h1>Ask about the Fed</h1></div>', unsafe_allow_html=True)
    st.markdown('<p class="lede">Ask in your own words. Answers are looked up in the Fed’s statements and economic data, '
                'and every number is checked before you see it.</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="note">Don’t enter personal information: questions go to free AI services that may use them to improve their models. '
                f'You can ask {config.SESSION_QUESTION_LIMIT} questions per visit.</p>', unsafe_allow_html=True)
    pending = None
    if not ss.chat:
        st.markdown('<p class="muted" style="margin:18px 0 2px">Not sure where to start?</p>', unsafe_allow_html=True)
        for q in ("Why did the Fed cut rates in September 2024?", "What would a quarter-point hike mean for my mortgage?",
                  "What is the Fed likely to do at its next meeting?"):
            if st.button(q, type="tertiary", key=f"ex_{q}"):
                pending = q
    for msg in ss.chat:
        with st.chat_message(msg["role"], avatar=None):
            st.markdown(msg["content"])
            if msg.get("label"):
                st.markdown(f'<div class="prov">{ui.E(msg["label"])}</div>', unsafe_allow_html=True)
    left = config.SESSION_QUESTION_LIMIT - ss.questions
    q = st.chat_input("Ask a question about the Fed" if left > 0 else "You’ve reached the question limit for this visit", disabled=left <= 0)
    q = q or pending
    if q and left > 0:
        ss.questions += 1
        with st.chat_message("user", avatar=None):
            st.markdown(q)
        hist = [{"role": m["role"], "content": m["content"]} for m in ss.chat][-2 * config.CHAT_HISTORY_TURNS:]
        with st.chat_message("assistant", avatar=None):
            with st.spinner("Looking it up"):
                try:
                    ans = agent.answer(q, history=hist)
                except Exception:
                    ans = agent.rules_answer(q)
            st.markdown(ans.text)
            label = ans.label + (" · from an earlier answer" if ans.cached else "")
            st.markdown(f'<div class="prov">{ui.E(label)}</div>', unsafe_allow_html=True)
        ss.chat += [{"role": "user", "content": q}, {"role": "assistant", "content": ans.text, "label": label}]


# ---------------------------------------------------------------- about
def page_about() -> None:
    bt = forecast_mod.backtest_summary() if forecast_mod.BACKTEST_PATH.exists() else {}
    n = len(dates())
    st.markdown('<div class="step" style="padding-top:28px"><h1>About Fed Decoder</h1></div>', unsafe_allow_html=True)
    st.markdown(f'''<div class="prose">
<p class="lede">Fed Decoder explains what the Federal Reserve decided, why, and what it means for you, for every one of its {n} policy statements since February 2000.</p>
<h3 class="gap">Where the numbers come from</h3>
<p>Decisions, votes and statement text come from the Federal Reserve. Economic data such as inflation, unemployment, Treasury yields and loan rates come from FRED, the St. Louis Fed’s public database. Every number on the page is calculated in code from that data, including loan payments, which use the standard amortization formula.</p>
<h3 class="gap">How the explanations are written</h3>
<p>The plain-English explanations are drafted by AI models on free plans (Google Gemini, with Groq as a backup). Before anything is shown, it is checked: every number must appear in the underlying data, and every quote must match the statement word for word. If a check fails, the app shows a simpler automated explanation instead.</p>
<h3 class="gap">Your privacy</h3>
<p>There are no accounts. Answers you give in “Work out your own numbers” stay in your browser tab and are never stored or sent to an AI. Questions you type on the Ask page are sent to free AI services, which may use them to improve their models, so please don’t include personal details.</p>
<h3 class="gap">What it can’t do</h3>
<p>Fed Decoder is for learning, not financial advice. Personal estimates use national averages, not your actual loan terms. The forecast is a simple statistical model{f": in tests on {bt['n']} past meetings it was right {bt['model_hit_rate'] * 100:.0f}% of the time, against {bt['baseline_hit_rate'] * 100:.0f}% for always guessing “no change”" if bt else ""}.</p>
</div>''', unsafe_allow_html=True)


{"Decode": page_decode, "Timeline": page_timeline, "Ask": page_ask, "About": page_about}[ss.nav]()
st.markdown(ui.footer_html(config.FOOTER), unsafe_allow_html=True)
