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


# ---------------------------------------------------------------- AI answers as working results
def _meeting_row(d: str, key: str) -> None:
    g = meetings().set_index(meetings()["meeting_date"].dt.strftime("%Y-%m-%d")).loc[d]
    gt = store.ground_truth().set_index("meeting_date").loc[pd.Timestamp(d)]
    vote = "" if pd.isna(gt["votes_for"]) else f" · {int(gt['votes_for'])}–{int(gt['votes_against'])}"
    c1, c2 = st.columns([4, 1], vertical_alignment="center")
    c1.markdown(f'<div class="res-row"><span class="res-date">{pd.Timestamp(d):%b %-d, %Y}</span>'
                f'<span class="res-move">{ui.E(ui.short_move(g["direction"], int(g["change_bps"])))}</span>'
                f'<span class="muted">{ui.fmt_range(g["target_low"], g["target_high"])}{vote}</span></div>', unsafe_allow_html=True)
    if c2.button("Open →", type="tertiary", key=key):
        open_meeting(d)
        st.rerun()


def render_results(calls: list[dict], key: str) -> None:
    """Show what the AI's tools returned (meetings, payments, charts, odds) instead of more prose."""
    from fed_decoder.chat import tools as T

    seen = set()
    for i, c in enumerate(calls or []):
        name, args = c.get("name"), c.get("args") or {}
        sig = name + repr(sorted(args.items()))
        if sig in seen:
            continue
        seen.add(sig)
        k = f"{key}_{i}"
        try:
            if name == "get_meeting":
                d = T.resolve_meeting(str(args.get("date", "")))
                if d is not None:
                    _meeting_row(str(d.date()), k)
            elif name == "notable_meetings":
                for j, m in enumerate(T.notable_meetings(args.get("kind", "split"), int(args.get("limit", 5)))["meetings"][:5]):
                    _meeting_row(m["meeting_date"], f"{k}_{j}")
            elif name == "payment_impact":
                r = T.payment_impact(**{a: args[a] for a in ("loan_type", "balance", "rate_change_bps", "base_rate_pct") if a in args})
                if "error" not in r:
                    label = {"mortgage_30y": "30-year mortgage", "auto_60m": "Car loan", "credit_card": "Credit card", "heloc": "Home equity line"}.get(r["loan_type"], r["loan_type"])
                    st.markdown(ui.tile(f"{label}, ${r['balance']:,.0f} at {r['base_rate_pct']:.2f}%", ui.signed_money(r["monthly_change"]),
                                        "", f"${r['monthly_before']:,.2f} → ${r['monthly_after']:,.2f} a month"), unsafe_allow_html=True)
            elif name == "my_impact" and ss.get("profile"):
                bps = int(args.get("rate_change_bps", 25))
                r = personal.personal_impact(ss.profile, bps, 0, pd.Timestamp.today())
                move = f"{'cut' if bps < 0 else 'hike'} of {abs(bps)} bp"
                st.markdown(ui.tile(f"You, after a {move}", ui.signed_money(r.monthly_total)), unsafe_allow_html=True)
                affected = [x for x in r.items if abs(x.get("monthly", 0)) >= 0.005]
                if affected:
                    st.markdown(ui.rows_html(affected), unsafe_allow_html=True)
            elif name == "get_series":
                r = T.get_series(**{a: args[a] for a in ("id", "start", "end") if a in args})
                if "error" not in r and r.get("points"):
                    import plotly.graph_objects as go_

                    from fed_decoder.ui import theme

                    xs = [p["date"] for p in r["points"]]
                    ys = [p["value"] for p in r["points"]]
                    fig = go_.Figure(go_.Scatter(x=xs, y=ys, mode="lines", line=dict(color=theme.GREEN, width=2),
                                                 hovertemplate="%{x}: %{y}<extra></extra>"))
                    fig.update_layout(height=200, margin=dict(l=4, r=4, t=26, b=4), paper_bgcolor=theme.IVORY, plot_bgcolor=theme.IVORY,
                                      title=dict(text=r["description"], font=dict(size=14, color=theme.MUTED), x=0),
                                      xaxis=dict(showgrid=False, tickfont=dict(size=12, color=theme.MUTED)),
                                      yaxis=dict(gridcolor="#ECE9E1", tickfont=dict(size=12, color=theme.MUTED)), font=dict(family="Inter"))
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=f"{k}_chart")
            elif name == "forecast_next":
                f = cached_forecast()
                p = {"hold": f["p_hold"], "cut": f["p_cut"], "hike": f["p_hike"]}
                top = max(p, key=p.get)
                st.markdown(ui.tile("Next meeting", f"{p[top] * 100:.0f}% {({'hold': 'hold', 'cut': 'cut', 'hike': 'raise'})[top]}", ui.odds_bar(p)),
                            unsafe_allow_html=True)
            elif name == "diff_statements":
                r = T.diff_statements(str(args.get("a", "")), str(args.get("b", "")))
                if "error" not in r:
                    html = "".join(f'<p class="res-diff">{"<del>" + ui.E(x["old"]) + "</del> " if x["old"] else ""}'
                                   f'{"<ins>" + ui.E(x["new"]) + "</ins>" if x["new"] else ""}</p>' for x in r["changes"][:3])
                    st.markdown(f'<div class="redline">{html}</div>', unsafe_allow_html=True)
            elif name == "search_statements":
                for j, hit in enumerate(T.search_statements(str(args.get("query", "")))["results"][:3]):
                    st.markdown(f'<div class="res-quote"><span class="res-date">{pd.Timestamp(hit["meeting_date"]):%b %-d, %Y}</span>'
                                f'<p>“{ui.E(hit["text"][:260])}{"…" if len(hit["text"]) > 260 else ""}”</p></div>', unsafe_allow_html=True)
            elif name == "fed_leadership":
                r = T.fed_leadership()
                if "error" not in r:
                    st.markdown('<div class="res-people">' + "".join(
                        f'<div><strong>{ui.E(m["name"])}</strong><span class="muted">{ui.E(m["title"])}</span></div>' for m in r["members"])
                        + "</div>", unsafe_allow_html=True)
        except Exception:
            continue


def answer_home_question(q: str) -> None:
    ss.questions += 1
    reader = personal.ai_labels(ss.profile) if (ss.get("ai_tailor") and ss.get("profile")) else None
    with st.spinner("Looking it up"):
        try:
            ans = agent.answer(q, reader=reader, has_profile=bool(ss.get("profile")))
        except Exception:
            ans = agent.rules_answer(q)
    ss.setdefault("home_thread", []).append({"q": q, "a": ans.text, "calls": ans.tool_calls})


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
    st.markdown('<p class="lede">Ask anything, or type a meeting: “latest”, “Sept 2024”.</p>', unsafe_allow_html=True)
    with st.form("ask_meeting", border=False, clear_on_submit=True):
        text = st.text_area("Question, meeting or statement", label_visibility="collapsed", height=90, max_chars=8000,
                            placeholder="For example: What is the Fed?  ·  latest  ·  Why did rates go up in 2022?")
        c1, _ = st.columns([1, 3])
        submitted = c1.form_submit_button("Go", type="primary", use_container_width=True)
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
        st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)
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
            render_results(item.get("calls", []), f"hres_{k}")
        shown = any(c.get("name") in ("get_meeting", "notable_meetings") for c in item.get("calls", []))
        for j, d in enumerate(meetings_mentioned(item["a"]) if not shown else []):
            if st.button(f"Open {pd.Timestamp(d):%b %-d, %Y} →", type="tertiary", key=f"goto_{k}_{j}_{d}"):
                open_meeting(d)
                st.rerun()
    st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)
    c1, c2, _ = st.columns([1, 1.25, 1.2])
    if c1.button(f"Latest meeting · {pd.Timestamp(dates()[-1]):%b %-d}", type="tertiary"):
        open_meeting(dates()[-1])
        st.rerun()
    if c2.button("All meetings since 2000", type="tertiary"):
        go("Timeline")
        st.rerun()


# ---------------------------------------------------------------- decoder sections
def for_you_items(card, ctx) -> list[dict]:
    facts = {b["topic"]: b for b in ctx["impacts"]["for_you"]}
    items = []
    for topic, label in (("Borrowers", "Credit cards"), ("Mortgages", "Mortgages"), ("Savers", "Savings"), ("Workers", "Jobs")):
        f = facts.get(topic)
        if f:
            items.append({"topic": label, "number": f["number"], "text": f["text"]})
    return items


def plain_what(d) -> str:
    if d.direction == "hold":
        p1 = f"Held the target range at {ui.fmt_range(d.target_low, d.target_high)}."
    else:
        p1 = f"{'Cut' if d.direction == 'cut' else 'Raised'} rates {abs(d.change_bps)} basis points, to {ui.fmt_range(d.target_low, d.target_high)}."
    vs = ui.vote_sentence(d)
    return p1 + (" " + vs if vs else "")


def when_of(ctx):
    return pd.Timestamp.today() if ctx["meeting_date"] == "pasted" else ctx["meeting_date"]


def ten_move(ctx):
    return ((ctx["impacts"].get("numbers") or {}).get("mortgage_30y") or {}).get("rate_change_bps")


HOUSING_TINY = {"rent": "Renter", "fixed": "Fixed mortgage", "arm": "Adjustable mortgage", "outright": "Own outright", "buying": "Buying soon"}
HOUSING_SHORT = {"rent": "I rent", "fixed": "I own, fixed-rate mortgage", "arm": "I own, adjustable-rate mortgage",
                 "outright": "I own outright", "buying": "I'm buying a home soon"}


@st.dialog("Your situation", width="large")
def profile_dialog() -> None:
    """All personal inputs. Kept only in this browser session; amounts never go to an AI."""
    p = ss.get("profile") or personal.Profile()
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
                   help="Shares only labels like “rents”. Never amounts, income or location.")
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


def prev_range(ctx, d) -> tuple[float, float]:
    if ctx["meeting_date"] != "pasted":
        g = store.ground_truth().set_index("meeting_date").loc[pd.Timestamp(ctx["meeting_date"])]
        return float(g["prev_low"]), float(g["prev_high"])
    return d.target_low - d.change_bps / 100, d.target_high - d.change_bps / 100


def next_meeting(ctx):
    if ctx["meeting_date"] == "pasted":
        return None
    all_d = dates()
    i = all_d.index(ctx["meeting_date"])
    if i + 1 >= len(all_d):
        return None
    nxt = all_d[i + 1]
    g = meetings().set_index(meetings()["meeting_date"].dt.strftime("%Y-%m-%d")).loc[nxt]
    return nxt, g["direction"], int(g["change_bps"])


def glance(card, ctx, is_latest: bool) -> None:
    """The whole meeting in four tiles: the move, you, the tone, what's next."""
    d = card.decision
    plo, phi = prev_range(ctx, d)
    prof = ss.get("profile")
    nm = next_meeting(ctx)
    fc = cached_forecast() if is_latest else None

    c1, c2, c3, c4 = st.columns([1, 1.15, 1, 1], gap="large")
    with c1:
        st.markdown(ui.tile("The decision", ui.short_move(d.direction, d.change_bps), ui.step_svg(plo, phi, d.target_low, d.target_high),
                            ui.fmt_range(d.target_low, d.target_high), "hawk" if d.change_bps > 0 else "dove" if d.change_bps < 0 else ""),
                    unsafe_allow_html=True)
    with c2:
        if prof is None:
            st.markdown('<div class="tile"><div class="tlab">For you</div><div class="tbig">Your costs?</div></div>', unsafe_allow_html=True)
            pick = st.selectbox("Your home", list(HOUSING_SHORT), index=None, format_func=HOUSING_SHORT.get,
                                placeholder="Pick your situation", label_visibility="collapsed", key=f"quick_{ss.get('nav_v', 0)}")
            if pick:
                ss.profile = personal.quick_profile(pick)
                ss.profile_typical = ["mortgage"] if pick in ("arm", "buying") else []
                st.rerun()
        else:
            r = personal.personal_impact(prof, d.change_bps, ten_move(ctx), when_of(ctx))
            if is_latest:
                up = personal.personal_impact(prof, 25, 0, when_of(ctx)).monthly_total
                cap = f"If they raise next: {ui.signed_money(up)}" if abs(up) >= 0.005 else "Not tied to the Fed’s rate"
            elif nm:
                nctx = cached_context(nm[0])
                nr = personal.personal_impact(prof, nm[2], ten_move(nctx), nm[0]).monthly_total
                cap = f"Next meeting: {ui.signed_money(nr)}"
            else:
                cap = ""
            big = ui.signed_money(r.monthly_total)
            st.markdown(ui.tile("For you", big, "", cap, "dove" if r.monthly_total < -0.005 else "hawk" if r.monthly_total > 0.005 else ""),
                        unsafe_allow_html=True)
            if st.button(HOUSING_TINY[prof.housing] + " · edit", type="tertiary", key="edit_prof"):
                profile_dialog()
    with c3:
        word, cls = ui.tone_words(card.tone_score)
        st.markdown(ui.tile("Tone", word.replace("Leaning ", "").capitalize(), ui.mini_scale(card.tone_score), "", cls), unsafe_allow_html=True)
    with c4:
        if fc:
            p = {"hold": fc["p_hold"], "cut": fc["p_cut"], "hike": fc["p_hike"]}
            top = max(p, key=p.get)
            st.markdown(ui.tile("Next meeting", f"{p[top] * 100:.0f}% {({'hold': 'hold', 'cut': 'cut', 'hike': 'raise'})[top]}", ui.odds_bar(p)),
                        unsafe_allow_html=True)
        elif nm:
            st.markdown(ui.tile("What happened next", ui.short_move(nm[1], nm[2]), "", f"{pd.Timestamp(nm[0]):%b %-d, %Y}",
                                "hawk" if nm[2] > 0 else "dove" if nm[2] < 0 else ""), unsafe_allow_html=True)


def three_things(card, ctx) -> None:
    d = card.decision
    things = [plain_what(d)]
    if card.changes:
        things.append(card.changes[0].explanation)
    if card.whats_next:
        things.append(re.split(r"(?<=\.)\s", card.whats_next.strip())[0])
    html = '<ol class="three">' + "".join(f"<li>{ui.define(ui.E(t), ['basis points', 'target range', 'dissented'])}</li>" for t in things[:3]) + "</ol>"
    st.markdown(html, unsafe_allow_html=True)


def ai_note(card, ctx) -> None:
    prof = ss.get("profile")
    if not prof:
        return
    if not ss.get("ai_tailor"):
        if st.button("Explain this for me", type="tertiary", key="ai_on", help="Shares only labels like “rents”. Never amounts."):
            ss.ai_tailor = True
            st.rerun()
        return
    from fed_decoder.cards.personal_note import personal_note

    r = personal.personal_impact(prof, card.decision.change_bps, ten_move(ctx), when_of(ctx))
    with st.spinner(""):
        note = None if agent.near_cap() else personal_note(ctx, personal.ai_labels(prof), personal.ai_effects(r))
    if note:
        two = " ".join(re.split(r"(?<=[.!?])\s+", note["text"].strip())[:2])
        st.markdown(f'<div class="ai-note reveal"><p>{ui.E(two)}</p></div>', unsafe_allow_html=True)


def suggested_questions(card, ctx) -> list[str]:
    d = card.decision
    qs = []
    if d.dissenters:
        qs.append(f"Why did {' and '.join(n.split()[-1] for n in d.dissenters[:2])} dissent?")
    qs.append({"hold": "Why hold?", "cut": "Why cut?", "hike": "Why raise?"}[d.direction])
    qs.append("What does this mean for mortgages?")
    return qs[:3]


def ask_block(card, ctx) -> None:
    key = ctx["meeting_date"]
    thread = ss.setdefault("threads", {}).setdefault(key, [])
    for n, item in enumerate(thread):
        q, a, calls = item[0], item[1], (item[3] if len(item) > 3 else [])
        with st.container(key=f"answer_m_{n}"):
            st.markdown(f'<div class="qa-q">{ui.E(q)}</div>', unsafe_allow_html=True)
            st.markdown(a)  # Markdown from the model; HTML is not allowed here
            render_results([c for c in calls if not (c.get("name") == "get_meeting")], f"mres_{key}_{n}")
    left = config.SESSION_QUESTION_LIMIT - ss.questions
    pending = None
    with st.form(f"ask_{key}", border=False, clear_on_submit=True):
        c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
        typed = c1.text_input("Ask", label_visibility="collapsed", placeholder="Ask anything about this meeting", disabled=left <= 0)
        sent = c2.form_submit_button("Ask", type="primary", use_container_width=True, disabled=left <= 0)
    if not thread and left > 0:
        with st.container(key="suggest"):
            cols = st.columns(3)
            for i, q in enumerate(suggested_questions(card, ctx)):
                if cols[i].button(q, type="tertiary", key=f"sq_{key}_{i}"):
                    pending = q
    q = pending or (typed.strip() if sent and typed else None)
    if q and left > 0:
        ss.questions += 1
        reader = personal.ai_labels(ss.profile) if (ss.get("ai_tailor") and ss.get("profile")) else None
        meeting = None if key == "pasted" else key
        with st.spinner(""):
            try:
                ans = agent.answer(q, meeting=meeting, reader=reader, has_profile=bool(ss.get("profile")))
            except Exception:
                ans = agent.rules_answer(q, meeting=meeting)
        thread.append((q, ans.text, ans.label, ans.tool_calls))
        st.rerun()


def section_changed(card, ctx) -> None:
    if not ctx.get("prev_statement"):
        st.markdown('<p class="muted">First statement on record.</p>', unsafe_allow_html=True)
        return
    pct = round((ctx.get("changed_fraction") or 0) * 100)
    ref = long_date(ctx["prev_meeting_date"])
    st.markdown(f'<p class="note">vs. {ref} · {pct}% reworded · <del class="key">removed</del> · <ins class="key">added</ins></p>', unsafe_allow_html=True)
    red, notes = ui.redline_html(ctx.get("prev_statement"), ctx["statement"], card.changes)
    st.markdown(f'<div class="margin-notes">{red}{ui.notes_html(notes)}</div>', unsafe_allow_html=True)


def section_tone(card, ctx) -> None:
    st.markdown(ui.tone_scale_html(card.tone_score), unsafe_allow_html=True)
    if card.tone_quotes:
        st.markdown(ui.quotes_html(card.tone_quotes[:3]), unsafe_allow_html=True)


def section_you(card, ctx) -> None:
    prof = ss.get("profile")
    if prof:
        r = personal.personal_impact(prof, card.decision.change_bps, ten_move(ctx), when_of(ctx))
        st.markdown(personal_breakdown_html(r), unsafe_allow_html=True)
        if st.button("Edit your situation", type="tertiary", key="edit_prof_tab"):
            profile_dialog()
    else:
        st.markdown('<p class="note">Typical household: $5,000 card balance, $300,000 mortgage, $10,000 savings.</p>'
                    + ui.rows_html(for_you_items(card, ctx)), unsafe_allow_html=True)


def personal_breakdown_html(r) -> str:
    affected = [i for i in r.items if abs(i.get("monthly", 0)) >= 0.005]
    unaffected = [i for i in r.items if abs(i.get("monthly", 0)) < 0.005 and i["topic"] != "Jobs where you live"]
    local = [i for i in r.items if i["topic"] == "Jobs where you live"]
    html = ""
    if affected:
        html += '<div class="bd-h">Changes</div>' + ui.rows_html(affected)
    if unaffected:
        html += '<div class="bd-h">No change</div>' + ui.rows_html(unaffected)
    if local:
        html += '<div class="bd-h">Where you live</div>' + ui.rows_html(local)
    return html


def section_economy(card, ctx) -> None:
    rows = [{"topic": b["topic"], "number": b["number"], "text": b["text"]} for b in ctx["impacts"]["for_country"]]
    st.markdown(ui.rows_html(rows), unsafe_allow_html=True)


def section_next(card, ctx, is_latest: bool) -> None:
    if is_latest:
        f = cached_forecast()
        bt = f["backtest"]
        st.markdown(ui.odds_html({"hold": f["p_hold"], "cut": f["p_cut"], "hike": f["p_hike"]}), unsafe_allow_html=True)
        st.markdown(f'<p class="note">Right {bt.get("model_hit_rate", 0) * 100:.0f}% of the time in backtests '
                    f'(always guessing “hold”: {bt.get("baseline_hit_rate", 0) * 100:.0f}%).</p>', unsafe_allow_html=True)
    elif ctx.get("forecast") and ctx["meeting_date"] != "pasted":
        fc = ctx["forecast"]
        st.markdown('<p class="note">What the model expected at the time</p>' + ui.odds_html({k: fc[k] / 100 for k in ("hold", "cut", "hike")}),
                    unsafe_allow_html=True)


def sources(card, ctx) -> None:
    st.markdown('<div class="redline">' + "".join(f"<p>{ui.E(p)}</p>" for p in ctx["statement"].split("\n\n")) + "</div>", unsafe_allow_html=True)
    cites = "".join(f'<li><span class="fig">{ui.E(c.source)}</span> {ui.E(c.detail)}</li>' for c in card.citations if c.source != "statement")
    if cites:
        st.markdown(f'<ul class="note">{cites}</ul>', unsafe_allow_html=True)


def decoder(card, ctx, is_latest: bool) -> None:
    d = card.decision
    when = (ss.get("pasted_label") or "Pasted statement") if ctx["meeting_date"] == "pasted" else long_date(ctx["meeting_date"])
    st.markdown(f'<div class="mhead"><div class="dateline">{when}</div><h1>{ui.E(ui.headline(d.direction, d.change_bps))}</h1></div>',
                unsafe_allow_html=True)
    glance(card, ctx, is_latest)
    ai_note(card, ctx)
    st.markdown('<div class="gap-l"></div>', unsafe_allow_html=True)
    three_things(card, ctx)
    ask_block(card, ctx)
    st.markdown('<div class="gap-l"></div>', unsafe_allow_html=True)
    tabs = st.tabs(["For you", "What changed", "Tone", "Economy", "Forecast", "Statement"])
    with tabs[0]:
        section_you(card, ctx)
    with tabs[1]:
        section_changed(card, ctx)
    with tabs[2]:
        section_tone(card, ctx)
    with tabs[3]:
        section_economy(card, ctx)
    with tabs[4]:
        section_next(card, ctx, is_latest)
    with tabs[5]:
        sources(card, ctx)
    if ctx["meeting_date"] != "pasted":
        all_d = dates()
        i = all_d.index(ctx["meeting_date"])
        with st.container(key="pager"):
            c1, c2 = st.columns(2)
            if i > 0 and c1.button(f"← {pd.Timestamp(all_d[i - 1]):%b %-d, %Y}", type="tertiary", key="pg_prev"):
                open_meeting(all_d[i - 1]); st.rerun()
            if i + 1 < len(all_d) and c2.button(f"{pd.Timestamp(all_d[i + 1]):%b %-d, %Y} →", type="tertiary", key="pg_next"):
                open_meeting(all_d[i + 1]); st.rerun()


def page_decode() -> None:
    if not ss.meeting:
        page_home()
        return
    if st.button("← All meetings", type="tertiary", key="restart_top"):
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
    st.markdown('<p class="lede">Each dot is a meeting, colored from <span class="dove">dovish</span> to <span class="hawk">hawkish</span>. Click one.</p>', unsafe_allow_html=True)
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
            if st.button("Open this meeting", type="primary"):
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
    rows = [
        ("Where the data comes from", f"Every Fed decision since 2000 ({len(dates())} statements). Figures come straight from the Federal Reserve "
                                      "and FRED, calculated in code."),
        ("The AI", "The Gemini API (Groq as backup) drafts the explanations. Every number and quote is checked."),
        ("Your privacy", "Nothing you enter is saved. Your situation is used only during your visit, and your amounts never go to an AI."),
    ]
    st.markdown('<div class="step" style="padding-top:28px"><h1>About</h1></div>'
                + '<div class="short about">' + "".join(f'<div class="short-row"><div class="aside-h">{k}</div><p>{ui.E(v)}</p></div>' for k, v in rows)
                + '</div><p class="byline">Built by Keith LoboPrabhu</p>', unsafe_allow_html=True)


{"Decode": page_decode, "Timeline": page_timeline, "About": page_about}[ss.nav]()
st.markdown(ui.footer_html(config.FOOTER), unsafe_allow_html=True)
