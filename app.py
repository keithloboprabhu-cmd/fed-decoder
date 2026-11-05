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

PAGES = ["Decode", "Timeline", "About"]
ss = st.session_state
ss.setdefault("nav", "Decode")
ss.setdefault("nav_v", 0)
ss.setdefault("meeting", None)       # "YYYY-MM-DD", "pasted", or None (home)
ss.setdefault("step", 0)
ss.setdefault("questions", 0)


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


@st.cache_data(show_spinner=False, ttl=1800)
def newer_statement() -> dict | None:
    """A statement in the Fed's RSS feed that's newer than our data (checked at most every 30 minutes)."""
    from fed_decoder.data.feed import statement_links

    try:
        links = statement_links(timeout=8)
    except Exception:
        return None
    latest = pd.Timestamp(dates()[-1]).date()
    new = [l for l in links if l.meeting_date > latest]
    return {"date": str(new[0].meeting_date), "url": new[0].url} if new else None


def open_live_statement(item: dict) -> None:
    """Decode a just-released statement on the spot (the scheduled update adds it to the archive later)."""
    from fed_decoder.data import fomc

    with st.spinner("Fetching the new statement from the Federal Reserve"):
        try:
            text = fomc.extract_statement_text(fomc._get(item["url"]))
        except Exception:
            text = ""
    if len(text) < 200:
        st.markdown('<p class="muted">The Federal Reserve’s site didn’t respond. Try again in a minute.</p>', unsafe_allow_html=True)
        return
    ss.pasted = text
    ss.pasted_label = f"Released {long_date(item['date'])} · just in"
    open_meeting("pasted")
    st.rerun()


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
QUESTION_START = re.compile(r"^(what|why|how|when|who|which|where|is|are|was|were|does|do|did|can|could|should|will|would|explain|tell|define)\b", re.I)


def interpret(text: str) -> tuple[str | None, str | None]:
    """Turn what someone typed into a meeting date, 'pasted', 'question', or an error message."""
    t = text.strip()
    if not t:
        return None, None
    all_dates = dates()
    if len(t) > 280 and re.search(r"\b(Committee|federal funds|FOMC)\b", t, re.I):
        return "pasted", None
    short_date = len(t) <= 30 and (parse_date(t) is not None or re.search(r"\b(latest|last meeting|most recent)\b", t, re.I))
    if not short_date and ("?" in t or QUESTION_START.match(t) or len(t.split()) > 5):
        return "question", None
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
        return "question", None  # anything else is treated as a question
    if when < pd.Timestamp("2000-01-01"):
        return None, "Fed Decoder covers meetings from February 2000 onward."
    if when > pd.Timestamp(all_dates[-1]) + pd.Timedelta(days=45):
        return None, f"There's no statement after {long_date(all_dates[-1])} yet."
    d = resolve_meeting(t)
    return (str(d.date()) if d is not None else None), None


STARTERS = ["What is the Fed, in plain English?", "Why does the Fed raise interest rates?", "What were the most controversial Fed decisions?"]


def meetings_mentioned(text: str) -> list[str]:
    """Meeting dates an answer mentions, so the reader can jump straight into them."""
    all_d = set(dates())
    found = []
    for m in re.finditer(r"\b(\d{4}-\d{2}-\d{2})\b|\b([A-Z][a-z]+ \d{1,2}, \d{4})\b", text):
        try:
            d = str(pd.Timestamp(m.group(1) or m.group(2)).date())
        except Exception:
            continue
        if d in all_d and d not in found:
            found.append(d)
    return found[:3]


def answer_home_question(q: str) -> None:
    ss.questions += 1
    reader = personal.ai_labels(ss.profile) if (ss.get("ai_tailor") and ss.get("profile")) else None
    with st.spinner("Looking it up"):
        try:
            ans = agent.answer(q, reader=reader)
        except Exception:
            ans = agent.rules_answer(q)
    ss.setdefault("home_thread", []).append({"q": q, "a": ans.text, "label": ans.label + (" · from an earlier answer" if ans.cached else "")})


def page_home() -> None:
    live = newer_statement()
    if live:
        with st.container(key="live"):
            c1, c2 = st.columns([3, 1], vertical_alignment="center")
            c1.markdown(f'<div class="live-t"><strong>New:</strong> the Fed released a statement on {long_date(live["date"])}.</div>', unsafe_allow_html=True)
            if c2.button("Decode it now", type="primary", key="live_go"):
                open_live_statement(live)
    st.markdown('<div style="height:6vh"></div>', unsafe_allow_html=True)
    st.markdown("<h1>What do you want to know about the Fed?</h1>", unsafe_allow_html=True)
    st.markdown('<p class="lede">Ask in plain words, or name a meeting such as “latest” or “September 2024”. '
                'You can also paste a Fed statement.</p>', unsafe_allow_html=True)
    with st.form("ask_meeting", border=False, clear_on_submit=True):
        text = st.text_area("Question, meeting or statement", label_visibility="collapsed", height=90, max_chars=8000,
                            placeholder="For example: What is the Fed?  ·  latest  ·  Why did rates go up in 2022?")
        c1, c2 = st.columns([1, 3], vertical_alignment="center")
        submitted = c1.form_submit_button("Go", type="primary", use_container_width=True)
        c2.markdown('<div class="note">Don’t enter personal information. Questions go to free AI services; pasted text is treated as data.</div>',
                    unsafe_allow_html=True)
    pending = None
    if submitted:
        target, err = interpret(text)
        if err:
            st.markdown(f'<p class="muted">{ui.E(err)}</p>', unsafe_allow_html=True)
        elif target == "pasted":
            ss.pasted = text
            ss.pop("pasted_label", None)
            open_meeting("pasted")
            st.rerun()
        elif target == "question":
            pending = text.strip()
        elif target:
            open_meeting(target)
            st.rerun()
    thread = ss.get("home_thread", [])
    if not thread and not pending:
        st.markdown('<p class="muted" style="margin:18px 0 0">New to this? Start here:</p>', unsafe_allow_html=True)
        with st.container(key="suggest_home"):
            for i, q in enumerate(STARTERS):
                if st.button(q, type="tertiary", key=f"starter_{i}"):
                    pending = q
    if pending:
        if config.SESSION_QUESTION_LIMIT - ss.questions <= 0:
            st.markdown('<p class="muted">You’ve reached the question limit for this visit.</p>', unsafe_allow_html=True)
        else:
            answer_home_question(pending)
            st.rerun()
    for k, item in enumerate(reversed(thread)):
        with st.container(key=f"answer_home_{k}"):
            st.markdown(f'<div class="qa-q">{"<br>".join(ui.E(x) for x in item["q"].split(chr(10)) if x.strip())}</div>', unsafe_allow_html=True)
            st.markdown(item["a"])  # Markdown from the model; HTML is not allowed here
            st.markdown(f'<div class="prov">{ui.E(item["label"])}</div>', unsafe_allow_html=True)
        for j, d in enumerate(meetings_mentioned(item["a"])):
            if st.button(f"Walk through the {long_date(d)} meeting →", type="tertiary", key=f"goto_{k}_{j}_{d}"):
                open_meeting(d)
                st.rerun()
    if ss.get("profile"):
        st.markdown(f'<p class="note" style="margin-top:10px">Explaining for you: {ui.E(personal.describe(ss.profile)).lower().replace("you ", "", 1)}.</p>',
                    unsafe_allow_html=True)
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


def meeting_header(card, ctx) -> None:
    d = card.decision
    when = (ss.get("pasted_label") or "Your pasted statement") if ctx["meeting_date"] == "pasted" else long_date(ctx["meeting_date"])
    st.markdown(f'<div class="step first"><div class="dateline">{when}</div>'
                f'<h1>{ui.E(ui.headline(d.direction, d.change_bps))}</h1>{ui.facts_html(d)}</div>', unsafe_allow_html=True)


def plain_what(d) -> str:
    if d.direction == "hold":
        p1 = f"The FOMC left the federal funds rate where it was, with the target range at {ui.fmt_range(d.target_low, d.target_high)}."
    else:
        p1 = (f"The FOMC {'lowered' if d.direction == 'cut' else 'raised'} the federal funds rate by {abs(d.change_bps)} basis points, "
              f"which moves the target range to {ui.fmt_range(d.target_low, d.target_high)}.")
    vs = ui.vote_sentence(d)
    return p1 + (" " + vs if vs else "")


# ---------------------------------------------------------------- you
HOUSING_SHORT = {"rent": "I rent", "fixed": "I own, fixed-rate mortgage", "arm": "I own, adjustable-rate mortgage",
                 "outright": "I own outright", "buying": "I'm buying a home soon"}


def when_of(ctx):
    return pd.Timestamp.today() if ctx["meeting_date"] == "pasted" else ctx["meeting_date"]


def ten_move(ctx):
    return ((ctx["impacts"].get("numbers") or {}).get("mortgage_30y") or {}).get("rate_change_bps")


@st.dialog("Your situation", width="large")
def profile_dialog() -> None:
    """All personal inputs. Kept only in this browser session; amounts never go to an AI."""
    p = ss.get("profile") or personal.Profile()
    st.markdown('<p class="note">Stays in this browser tab. Nothing is saved, and amounts are never sent to an AI. '
                'Leave anything blank to use a typical amount.</p>', unsafe_allow_html=True)
    st.markdown('<div class="qa">Where do you live?</div>', unsafe_allow_html=True)
    with st.container(key="tiles_dlg_housing"):
        housing = st.radio("Housing", list(HOUSING_SHORT), index=list(HOUSING_SHORT).index(p.housing),
                           format_func=HOUSING_SHORT.get, label_visibility="collapsed", key="dlg_housing")
    mort = None
    if housing in ("arm", "buying"):
        mort = st.number_input("Mortgage balance" if housing == "arm" else "How much you plan to borrow", min_value=0, step=10_000,
                               value=int(p.mortgage_balance) or None, placeholder=f"Typical: {personal.TYPICAL['mortgage']:,}", key="dlg_mort")
    st.markdown('<div class="qa">What else do you have?</div>', unsafe_allow_html=True)
    with st.container(key="checks_dlg"):
        c1, c2 = st.columns(2)
        has_card = c1.checkbox("A credit card balance I carry", value=bool(p.card_balance), key="dlg_has_card")
        has_heloc = c2.checkbox("A home equity line", value=bool(p.heloc_balance), key="dlg_has_heloc")
        has_stud = c1.checkbox("A variable-rate private student loan", value=bool(p.private_student_variable), key="dlg_has_stud")
        shop_car = c2.checkbox("I'm shopping for a car loan", value=p.car_loan == "shopping", key="dlg_car_shop")
        fixed_car = c1.checkbox("A fixed-rate car loan", value=p.car_loan == "have_fixed", key="dlg_car_fixed")
        has_sav = c2.checkbox("Savings", value=bool(p.savings), key="dlg_has_sav")
    amounts = {}
    cols = st.columns(2)
    k = 0
    for flag, key, label, cur, typ in ((has_card, "card", "Card balance", p.card_balance, "card"),
                                       (has_heloc, "heloc", "Home equity balance", p.heloc_balance, "heloc"),
                                       (has_stud, "stud", "Student loan balance", p.private_student_variable, "student"),
                                       (shop_car, "car", "Car loan amount", p.car_amount, "car"),
                                       (has_sav, "sav", "Savings", p.savings, "savings")):
        if flag:
            amounts[key] = cols[k % 2].number_input(label, min_value=0, step=500, value=int(cur) or None,
                                                    placeholder=f"Typical: {personal.TYPICAL[typ]:,}", key=f"dlg_{key}")
            k += 1
    sav_kind = p.savings_kind
    if has_sav:
        sav_kind = st.radio("Where are your savings?", list(personal.SAVINGS_KIND), index=list(personal.SAVINGS_KIND).index(p.savings_kind),
                            format_func=personal.SAVINGS_KIND.get, horizontal=True, key="dlg_sav_kind")
    with st.expander("Put it in context (optional)"):
        c1, c2 = st.columns(2)
        income = c1.selectbox("Household income", list(personal.INCOME), index=list(personal.INCOME).index(p.income), key="dlg_income")
        states = [None] + list(config.STATES)
        state = c2.selectbox("State, for local jobs data", states, index=states.index(p.state), key="dlg_state",
                             format_func=lambda x: "Prefer not to say" if x is None else config.STATES[x])
    ai = st.toggle("Let AI tailor explanations to my situation", value=ss.get("ai_tailor", False), key="dlg_ai",
                   help="Shares only broad categories such as “rents” or “carries a card balance” with the AI provider. Never amounts, income or location.")
    c1, c2 = st.columns([1, 1])
    if c1.button("Save", type="primary", use_container_width=True):
        typical = []

        def amt(key, typ):
            v = amounts.get(key)
            if v is None:
                typical.append(typ)
                return float(personal.TYPICAL[typ])
            return float(v)
        mort_v = 0.0
        if housing in ("arm", "buying"):
            mort_v = float(mort) if mort else float(personal.TYPICAL["mortgage"])
            if not mort:
                typical.append("mortgage")
        ss.profile = personal.Profile(
            housing=housing, mortgage_balance=mort_v,
            card_balance=amt("card", "card") if has_card else 0.0, heloc_balance=amt("heloc", "heloc") if has_heloc else 0.0,
            private_student_variable=amt("stud", "student") if has_stud else 0.0,
            car_loan="shopping" if shop_car else "have_fixed" if fixed_car else "none", car_amount=amt("car", "car") if shop_car else 0.0,
            savings=amt("sav", "savings") if has_sav else 0.0, savings_kind=sav_kind, income=income, state=state)
        ss.profile_typical = typical
        ss.ai_tailor = ai
        st.rerun()
    if ss.get("profile") and c2.button("Forget my answers", type="tertiary"):
        for k_ in ("profile", "profile_typical", "ai_tailor"):
            ss.pop(k_, None)
        st.rerun()


def money(x: float) -> str:
    return f"${abs(x):,.2f}"


def personal_block(card, ctx, is_latest: bool) -> None:
    d = card.decision
    prof = ss.get("profile")
    if prof is None:
        st.markdown('<div class="you-q"><h2>What does this mean for you?</h2>'
                    '<p class="muted" style="margin:0 0 14px">Tap the one that fits. You’ll get your own numbers right away; '
                    'nothing leaves this browser tab.</p></div>', unsafe_allow_html=True)
        with st.container(key="tiles_quick"):
            pick = st.radio("Housing", list(HOUSING_SHORT), index=None, format_func=HOUSING_SHORT.get,
                            label_visibility="collapsed", key=f"quick_{ss.get('nav_v', 0)}")
        if pick:
            ss.profile = personal.quick_profile(pick)
            ss.profile_typical = ["mortgage"] if pick in ("arm", "buying") else []
            st.rerun()
        with st.expander("Or see a typical household first"):
            st.markdown('<p class="note">Example balances: a $5,000 credit card balance, a $300,000 mortgage and $10,000 in savings.</p>'
                        + ui.rows_html(for_you_items(card, ctx)), unsafe_allow_html=True)
        return

    r = personal.personal_impact(prof, d.change_bps, ten_move(ctx), when_of(ctx))
    affected = [i for i in r.items if abs(i.get("monthly", 0)) >= 0.005]
    if d.change_bps == 0 or not affected:
        big = "Your monthly costs don’t change"
        sub = "Nothing you pay or earn that follows the Fed moved with this decision."
        if prof.housing == "buying" and affected:
            big = "Your costs follow the 10-year Treasury, not this decision"
    else:
        verb = "fall" if r.monthly_total < 0 else "rise"
        big = f"Your costs {verb} by about {money(r.monthly_total)} a month"
        names = ", ".join(i["topic"].lower() for i in affected)
        sub = f"Mostly through your {names}."
        if r.share_of_income is not None:
            sub += f" That’s about {abs(r.share_of_income):.2f}% of your monthly income."
    with st.container(key="you"):
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        c1.markdown(f'<div class="who">{ui.E(personal.describe(prof))}</div>', unsafe_allow_html=True)
        if c2.button("Edit your situation", type="tertiary", key="edit_prof"):
            profile_dialog()
        st.markdown(f'<div class="you-big reveal">{ui.E(big)}</div><p class="you-sub">{ui.E(sub)}</p>', unsafe_allow_html=True)

        # AI note: only broad labels, only with opt-in
        if ss.get("ai_tailor"):
            from fed_decoder.cards.personal_note import personal_note

            with st.spinner("Tailoring this to you"):
                note = None if agent.near_cap() else personal_note(ctx, personal.ai_labels(prof), personal.ai_effects(r))
            if note:
                who = {"gemini": "Gemini", "groq": "Groq"}.get(note["provider"], note["provider"])
                st.markdown(f'<div class="ai-note"><p>{ui.E(note["text"])}</p><span class="note">Written by {who} from broad categories only; '
                            'numbers come from code.</span></div>', unsafe_allow_html=True)
        else:
            if st.button("Explain it for my situation with AI", type="tertiary", key="ai_on",
                         help="Shares only broad categories such as “rents” or “carries a card balance”. Never amounts, income or location."):
                ss.ai_tailor = True
                st.rerun()

        # What the next move would mean for this person
        up = personal.personal_impact(prof, 25, 0, when_of(ctx)).monthly_total
        down = personal.personal_impact(prof, -25, 0, when_of(ctx)).monthly_total
        if is_latest:
            fc = cached_forecast()
            lines = []
            if abs(up) >= 0.005 or abs(down) >= 0.005:
                lines.append(f"If the Fed raises rates a quarter point next time (our model puts that at {fc['p_hike'] * 100:.0f}%), "
                             f"your costs would rise about {money(up)} a month. If it cuts ({fc['p_cut'] * 100:.0f}%), they’d fall about {money(down)}.")
            else:
                lines.append("A quarter-point move either way wouldn’t change your monthly costs much, because what you have isn’t tied to the Fed’s rate.")
            st.markdown('<div class="next-you"><div class="aside-h">Next meeting</div><p>' + ui.E(" ".join(lines)) + '</p></div>', unsafe_allow_html=True)
        elif ctx["meeting_date"] != "pasted":
            all_d = dates()
            i = all_d.index(ctx["meeting_date"])
            if i + 1 < len(all_d):
                nxt = all_d[i + 1]
                g = meetings().set_index(meetings()["meeting_date"].dt.strftime("%Y-%m-%d")).loc[nxt]
                nctx = cached_context(nxt)
                nr = personal.personal_impact(prof, int(g["change_bps"]), ten_move(nctx), nxt)
                what = ui.headline(g["direction"], int(g["change_bps"]))
                what = what[0].lower() + what[1:]
                eff = ("which didn’t change your costs" if abs(nr.monthly_total) < 0.005 else
                       f"which would have {'lowered' if nr.monthly_total < 0 else 'raised'} your costs about {money(nr.monthly_total)} a month")
                st.markdown(f'<div class="next-you"><div class="aside-h">What happened next</div><p>On {long_date(nxt)}, {what}, {eff}.</p></div>',
                            unsafe_allow_html=True)

        with st.expander("See how we worked this out"):
            st.markdown(personal_breakdown_html(r), unsafe_allow_html=True)
            typ = ss.get("profile_typical") or []
            if typ:
                st.markdown(f'<p class="note">Using typical amounts for: {", ".join(typ)}. Edit your situation to use your own.</p>', unsafe_allow_html=True)


def personal_breakdown_html(r) -> str:
    affected = [i for i in r.items if abs(i.get("monthly", 0)) >= 0.005]
    unaffected = [i for i in r.items if abs(i.get("monthly", 0)) < 0.005 and i["topic"] != "Jobs where you live"]
    local = [i for i in r.items if i["topic"] == "Jobs where you live"]
    html = ""
    if affected:
        html += '<div class="bd-h">Changes with this decision</div>' + ui.rows_html(affected)
    if unaffected:
        html += '<div class="bd-h">Doesn’t change</div>' + ui.rows_html(unaffected)
    if local:
        html += '<div class="bd-h">Where you live</div>' + ui.rows_html(local)
    html += '<p class="note" style="margin-top:10px">Estimates use national average rates, not your actual loan terms. Not financial advice.</p>'
    return html


# ---------------------------------------------------------------- the short version and asking
def summary_block(card, ctx) -> None:
    d = card.decision
    items = [("What happened", ui.define(ui.E(plain_what(d)), ["FOMC", "federal funds rate", "basis points", "target range", "dissented"]))]
    if card.tone_quotes:
        items.append(("In the Fed’s words", f'<span class="say-inline">“{ui.E(card.tone_quotes[0].quote)}”</span>'))
    items.append(("What it signals", ui.E(card.whats_next)))
    html = '<div class="short"><h3>The short version</h3>' + "".join(
        f'<div class="short-row"><div class="aside-h">{k}</div><p>{v}</p></div>' for k, v in items) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


def suggested_questions(card, ctx) -> list[str]:
    d = card.decision
    qs = []
    if d.dissenters:
        names = " and ".join(n.split()[-1] for n in d.dissenters[:2])
        qs.append(f"Why did {names} dissent?")
    qs.append({"hold": "Why did the Fed hold rates?", "cut": "Why did the Fed cut rates?", "hike": "Why did the Fed raise rates?"}[d.direction])
    if card.changes:
        qs.append("What's the most important change in the wording?")
    prof = ss.get("profile")
    if prof and prof.housing in ("buying", "arm"):
        qs.append("What does this mean for mortgage rates?")
    elif prof and prof.card_balance:
        qs.append("Will my credit card rate change?")
    else:
        qs.append("Will rates go up or down next?")
    return qs[:3]


def ask_block(card, ctx) -> None:
    key = ctx["meeting_date"]
    thread = ss.setdefault("threads", {}).setdefault(key, [])
    st.markdown('<div class="ask"><h3>Ask about this meeting</h3></div>', unsafe_allow_html=True)
    if agent.near_cap():
        st.markdown('<p class="note">The free AI allowance for today is used up, so answers are automated from the statement until tomorrow.</p>',
                    unsafe_allow_html=True)
    for n, (q, a, label) in enumerate(thread):
        with st.container(key=f"answer_m_{n}"):
            st.markdown(f'<div class="qa-q">{ui.E(q)}</div>', unsafe_allow_html=True)
            st.markdown(a)  # Markdown from the model; HTML is not allowed here
            st.markdown(f'<div class="prov">{ui.E(label)}</div>', unsafe_allow_html=True)
    left = config.SESSION_QUESTION_LIMIT - ss.questions
    pending = None
    if not thread and left > 0:
        with st.container(key="suggest"):
            for i, q in enumerate(suggested_questions(card, ctx)):
                if st.button(q, type="tertiary", key=f"sq_{key}_{i}"):
                    pending = q
    with st.form(f"ask_{key}", border=False, clear_on_submit=True):
        c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
        typed = c1.text_input("Your question", label_visibility="collapsed",
                              placeholder="Ask anything about this decision" if left > 0 else "Question limit reached for this visit",
                              disabled=left <= 0)
        sent = c2.form_submit_button("Ask", type="primary", use_container_width=True, disabled=left <= 0)
    st.markdown('<p class="note" style="margin-top:-6px">Questions go to free AI services, so don’t include personal details.</p>', unsafe_allow_html=True)
    q = pending or (typed.strip() if sent and typed else None)
    if q and left > 0:
        ss.questions += 1
        reader = personal.ai_labels(ss.profile) if (ss.get("ai_tailor") and ss.get("profile")) else None
        meeting = None if key == "pasted" else key
        with st.spinner("Looking it up"):
            try:
                ans = agent.answer(q, meeting=meeting, reader=reader)
            except Exception:
                ans = agent.rules_answer(q, meeting=meeting)
        thread.append((q, ans.text, ans.label + (" · from an earlier answer" if ans.cached else "")))
        st.rerun()


def section_changed(card, ctx) -> None:
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


def section_economy(card, ctx) -> None:
    st.markdown('<div class="prose"><p>The Fed’s two jobs are stable prices and maximum employment. Here is where things stood, '
                'using the data that was public at the time.</p></div>', unsafe_allow_html=True)
    rows = []
    for b in ctx["impacts"]["for_country"]:
        llm = next((x.text for x in card.for_country if x.topic.lower() == b["topic"].lower()), None)
        rows.append({"topic": b["topic"], "number": b["number"], "text": llm if (llm and card.provider != "rules") else b["text"]})
    st.markdown(ui.briefing_html(rows), unsafe_allow_html=True)


def section_next(card, ctx, is_latest: bool) -> None:
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
    if True:
        st.markdown(f'<p class="note">{ui.E(provider_note(card))}</p>', unsafe_allow_html=True)
        st.markdown('<div class="redline">' + "".join(f"<p>{ui.E(p)}</p>" for p in ctx["statement"].split("\n\n")) + "</div>", unsafe_allow_html=True)
        cites = "".join(f'<li><span class="fig">{ui.E(c.source)}</span>: {ui.E(c.detail)}</li>' for c in card.citations if c.source != "statement")
        if cites:
            st.markdown(f'<p class="note" style="margin-top:8px">Data used</p><ul class="note">{cites}</ul>', unsafe_allow_html=True)


def decoder(card, ctx, is_latest: bool) -> None:
    meeting_header(card, ctx)
    personal_block(card, ctx, is_latest)
    summary_block(card, ctx)
    ask_block(card, ctx)
    st.markdown('<div class="deeper-h"><h3>Go deeper</h3></div>', unsafe_allow_html=True)
    tabs = st.tabs(["What changed", "How the Fed sounded", "The economy", "What’s next", "Sources"])
    with tabs[0]:
        section_changed(card, ctx)
    with tabs[1]:
        section_tone(card, ctx)
    with tabs[2]:
        section_economy(card, ctx)
    with tabs[3]:
        section_next(card, ctx, is_latest)
    with tabs[4]:
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
            if ss.get("profile"):
                pr = personal.personal_impact(ss.profile, int(g["change_bps"]), ten_move(cached_context(pick)), pick)
                eff = ("It didn’t change your monthly costs." if abs(pr.monthly_total) < 0.005 else
                       f"For you: about {money(pr.monthly_total)} a month {'less' if pr.monthly_total < 0 else 'more'}.")
                st.markdown(f'<p style="margin:6px 0 0">{ui.E(eff)}</p>', unsafe_allow_html=True)
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
def page_about() -> None:
    bt = forecast_mod.backtest_summary() if forecast_mod.BACKTEST_PATH.exists() else {}
    fc = f"The forecast was right {bt['model_hit_rate'] * 100:.0f}% of the time in tests, vs {bt['baseline_hit_rate'] * 100:.0f}% for guessing “no change”." if bt else ""
    rows = [
        ("What it is", f"Every Fed decision since 2000 ({len(dates())} statements), explained for your situation."),
        ("The numbers", "From the Federal Reserve and FRED, calculated in code. Never written by AI."),
        ("The AI", "Gemini (Groq as backup) drafts the explanations. Every number and quote is checked; if a check fails, you get a simpler automated version."),
        ("Your privacy", "No accounts. Your situation stays in this tab and is never stored. Amounts never go to an AI; the optional AI note sees only labels like “rents”."),
        ("Limits", "Learning, not financial advice. Estimates use national averages. " + fc),
    ]
    st.markdown('<div class="step" style="padding-top:28px"><h1>About</h1></div>'
                + '<div class="short about">' + "".join(f'<div class="short-row"><div class="aside-h">{k}</div><p>{ui.E(v)}</p></div>' for k, v in rows)
                + "</div>", unsafe_allow_html=True)


{"Decode": page_decode, "Timeline": page_timeline, "About": page_about}[ss.nav]()
st.markdown(ui.footer_html(config.FOOTER), unsafe_allow_html=True)
