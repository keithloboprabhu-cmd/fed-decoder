"""Fed Decoder, "The Staircase" UI.

Presentation only. Every number comes from the data and calculation layers
(fed_decoder.data / analysis / cards); explanations come from the validated
decoder cards and are shortened by code at render time. Personal choices stay in
this session and never reach an AI.
"""
from __future__ import annotations

import re
from datetime import date

import pandas as pd
import streamlit as st

from fed_decoder import config
from fed_decoder.analysis import forecast as forecast_mod
from fed_decoder.analysis import impact, personal
from fed_decoder.analysis.votes import dissent_details, voters
from fed_decoder.cards.builder import build_llm_card
from fed_decoder.cards.context import build_context, build_context_pasted
from fed_decoder.cards.rules import build_rules_card
from fed_decoder.cards.store import all_cards, load_card
from fed_decoder.chat import agent
from fed_decoder.chat.tools import parse_date, resolve_meeting
from fed_decoder.data import store
from fed_decoder.ui import components as ui
from fed_decoder.ui import theme
from fed_decoder.ui.staircase import staircase
from fed_decoder.ui.theme import CSS

st.set_page_config(page_title="Fed Decoder", page_icon=None, layout="wide", initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)

ss = st.session_state
ss.setdefault("page", "meeting")
ss.setdefault("meeting", None)       # "YYYY-MM-DD" or "pasted"; None means the latest meeting
ss.setdefault("open_card", None)
ss.setdefault("mine", [])
ss.setdefault("questions", 0)
ss.setdefault("stair_n", 0)


# ---------------------------------------------------------------- cached data
@st.cache_data(show_spinner=False)
def meetings() -> pd.DataFrame:
    return store.ground_truth()[["meeting_date", "direction", "change_bps", "target_low", "target_high", "prev_low", "prev_high"]].copy()


def dates() -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in meetings()["meeting_date"]]


@st.cache_data(show_spinner=False)
def tones() -> dict[str, float]:
    return {d: c.tone_score for d, c in all_cards().items()}


@st.cache_data(show_spinner=False, ttl=3600)
def cached_forecast() -> dict:
    return forecast_mod.forecast_next().to_dict()


@st.cache_data(show_spinner=False)
def features() -> pd.DataFrame:
    f = forecast_mod.build_features()
    f["key"] = f["meeting_date"].dt.strftime("%Y-%m-%d")
    return f.set_index("key")


@st.cache_data(show_spinner=False)
def cached_context(date_str: str) -> dict:
    return build_context(date_str)


@st.cache_data(show_spinner=False)
def stair_data() -> list[dict]:
    out = []
    for r in meetings().itertuples():
        out.append({"d": r.meeting_date.strftime("%Y-%m-%d"), "lo": float(r.target_low), "hi": float(r.target_high), "c": int(r.change_bps),
                    "lab": f"{ui.short_move(r.direction, r.change_bps)} · {ui.fmt_range(r.target_low, r.target_high)}"})
    return out


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


def open_meeting(m: str | None) -> None:
    ss.meeting = m
    ss.page = "meeting"
    ss.open_card = None


def current() -> str:
    return ss.meeting or dates()[-1]


def long_date(d: str) -> str:
    return f"{pd.Timestamp(d):%B %-d, %Y}"


def short_date(d: str) -> str:
    return f"{pd.Timestamp(d):%b %-d, %Y}"


# ---------------------------------------------------------------- routing what people type
MONTHS_RX = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
LATEST_RX = re.compile(r"\b(last|latest|most recent|recent|newest|this week'?s|today'?s|current)\b[^?.]*\b(meeting|decision|statement|fomc|announcement|move)\b"
                       r"|\b(meeting|decision|statement|fomc)\b[^?.]*\b(last|latest|most recent)\b|^(latest|last|newest)$", re.I)
GENERIC_RX = re.compile(r"\bwhat (happened|did (the fed|they|the fomc) (do|decide|announce)|was (decided|announced))|\b(tell me about|summar|recap|"
                        r"overview|explain|break ?down|walk me through|decode)\b|^what('s| is) new", re.I)


def meeting_reference(t: str) -> str | None:
    """The single meeting a piece of text points at, or None. Needs 'latest/last meeting' or a month (a year alone
    spans several meetings, so 'what happened in 2022' stays a general question)."""
    all_dates = dates()
    tl = t.lower()
    m = re.search(r"\blast (january|february|march|april|may|june|july|august|september|october|november|december)\b", tl)
    if m:
        latest = pd.Timestamp(all_dates[-1])
        month = pd.Timestamp(f"1 {m.group(1)} 2000").month
        year = latest.year if month <= latest.month else latest.year - 1
        d = resolve_meeting(f"{m.group(1)} {year}")
        return str(d.date()) if d is not None else None
    if LATEST_RX.search(t):
        return all_dates[-1]
    if re.search(r"\d{4}-\d{1,2}(-\d{1,2})?", t) or re.search(MONTHS_RX + r"\.?,?\s+(\d{1,2},?\s+)?\d{4}", tl):
        when = parse_date(t)
        if when is None or when < pd.Timestamp("2000-01-01") or when > pd.Timestamp(all_dates[-1]) + pd.Timedelta(days=45):
            return None
        d = resolve_meeting(t)
        return str(d.date()) if d is not None else None
    return None


def interpret(text: str) -> tuple[str | None, str | None]:
    """Route what someone typed: ('pasted', None), ('question', None), (date, None) to open a meeting,
    (date, question) to open a meeting and answer the question there, or (None, error)."""
    t = text.strip()
    if not t:
        return None, None
    if len(t) > 280 and re.search(r"\b(Committee|federal funds|FOMC)\b", t, re.I):
        return "pasted", None
    ref = meeting_reference(t)
    if ref:
        words = len(re.findall(r"\w+", t))
        if words <= 6 or GENERIC_RX.search(t):
            return ref, None          # "latest", "September 2024", "what happened at the last meeting"
        return ref, t                 # a specific question about one meeting: open it and answer there
    if parse_date(t) is not None and len(t) <= 30 and not re.search(r"[?]|\b(what|why|how)\b", t, re.I):
        when = parse_date(t)
        if when < pd.Timestamp("2000-01-01"):
            return None, "Fed Decoder covers meetings from February 2000 onward."
    return "question", None


# ---------------------------------------------------------------- top bar, live strip, staircase
def top_bar() -> None:
    with st.container(key="topbar"):
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.markdown('<div class="brand">Fed Decoder</div>', unsafe_allow_html=True)
        label = "← Back" if ss.page == "about" else "About"
        if c2.button(label, type="tertiary", key="about_btn"):
            ss.page = "meeting" if ss.page == "about" else "about"
            st.rerun()


def spark_series(sid: str, months: int = 24, yoy: bool = False, until=None) -> list[float]:
    s = store.series(sid)
    if until is not None:
        s = s[s.index <= pd.Timestamp(until)]
    if yoy:
        s = (s / s.shift(12 if sid != "GDPC1" else 4) - 1) * 100
    s = s.dropna()
    if len(s) > 400:  # daily series -> month ends
        s = s.resample("ME").last().dropna()
    return [float(v) for v in s.iloc[-months:]]


def live_strip() -> None:
    from fed_decoder.data.calendar import next_meeting

    items = []
    nm = next_meeting()
    if nm:
        days = (pd.Timestamp(nm["date"]).date() - date.today()).days
        when = "today" if days == 0 else f"in {days} days"
        sep = " · with projections (SEP)" if nm.get("sep") else ""
        items.append(f'<span class="it" tabindex="0">Next meeting <b>{when}</b><span class="pop">{long_date(nm["date"])}{sep}. '
                     f'Source: federalreserve.gov calendar.</span></span>')
    cpi = store.yoy_asof("CPIAUCSL", pd.Timestamp.today() + pd.Timedelta(days=35))
    ur = store.value_asof("UNRATE", pd.Timestamp.today() + pd.Timedelta(days=35))
    ten = store.value_asof("DGS10", pd.Timestamp.today(), lagged=False)
    for lab, val, sid, yoy, fmt in (("CPI", cpi, "CPIAUCSL", True, "%b %Y"), ("Jobless", ur, "UNRATE", False, "%b %Y"), ("10-yr", ten, "DGS10", False, "%b %-d")):
        if val:
            spark = ui.sparkline(spark_series(sid, 24, yoy), 180, 40)
            items.append(f'<span class="it" tabindex="0">{lab} <b>{val[1]:.1f}%</b><span class="pop">{spark}<br>{lab} {val[1]:.2f}% · '
                         f'{val[0]:{fmt}} · FRED {sid}</span></span>')
    if ten:
        items.append(f'<span class="it">Updated <b>{ten[0]:%b %-d}</b></span>')
    live = newer_statement()
    if live:
        items.append(f'<span class="it new">New statement {short_date(live["date"])} ↓</span>')
    st.markdown('<div class="live">' + "".join(items) + "</div>", unsafe_allow_html=True)
    if live and st.button(f"Decode the {short_date(live['date'])} statement", type="tertiary", key="live_go"):
        from fed_decoder.data import fomc

        try:
            text = fomc.extract_statement_text(fomc._get(live["url"]))
        except Exception:
            text = ""
        if len(text) > 200:
            ss.pasted, ss.pasted_label = text, f"{long_date(live['date'])} · just released"
            open_meeting("pasted")
            st.rerun()


def stair() -> None:
    sel = None if ss.meeting == "pasted" else current()
    v = staircase(stair_data(), sel, date.today(), key="stair")
    if v and v.get("n", 0) != ss.stair_n:
        ss.stair_n = v["n"]
        if v.get("date") and (v["date"] != current() or ss.page != "meeting"):
            open_meeting(v["date"])
            st.rerun()


# ---------------------------------------------------------------- verdict
def prev_tones(d: str | None, n: int = 6) -> list[float]:
    all_d = dates()
    i = all_d.index(d) if d in all_d else len(all_d)
    return [tones()[x] for x in all_d[max(0, i - n):i] if x in tones()]


def next_of(d: str):
    all_d = dates()
    if d not in all_d:
        return None
    i = all_d.index(d)
    if i + 1 >= len(all_d):
        return None
    g = meetings().set_index(meetings()["meeting_date"].dt.strftime("%Y-%m-%d")).loc[all_d[i + 1]]
    return all_d[i + 1], g["direction"], int(g["change_bps"])


def verdict(card, ctx) -> None:
    d = card.decision
    text = ctx["statement"]
    details = dissent_details(text, d.direction, list(d.dissenters), int(d.change_bps)) if d.dissenters else []
    when = (ss.get("pasted_label") or "Pasted statement") if ctx["meeting_date"] == "pasted" else long_date(ctx["meeting_date"])
    chip, cls = ui.arrow_chip(d.direction, d.change_bps)
    prev = prev_tones(None if ctx["meeting_date"] == "pasted" else ctx["meeting_date"])
    _, tcls = ui.tone_words(card.tone_score)
    if d.votes_for is not None:
        vote = (ui.vote_dots(int(d.votes_for), details, voters(text))
                + f'<div class="vcap" title="{int(d.votes_for)} for, {int(d.votes_against)} against (hollow dots). Source: the statement’s voting record">{int(d.votes_for)}–{int(d.votes_against)}</div>')
    else:
        vote = '<div class="vcap" style="font-size:20px">—</div><div class="mini">Votes weren’t published before 2002</div>'
    range_lab = ui.term("Target range", "target range")
    vote_lab = "Vote"
    head = ui.E(ui.verdict_headline(d, details))
    rng = ui.fmt_range(d.target_low, d.target_high)
    stripe = ui.tone_stripe(card.tone_score, prev)
    tcap = ui.E(ui.tone_caption(card.tone_score, prev))
    st.markdown(f'<div class="verdict glide"><div class="dateline">{when}</div><h1>{head}</h1></div>', unsafe_allow_html=True)
    nx = next_of(ctx["meeting_date"]) if ctx["meeting_date"] != "pasted" else None
    with st.container(key="facts"):
        c1, c2, c3, c4 = st.columns([1.15, 1, 1.1, 1.0], gap="large")
        c1.markdown(f'<div class="fact"><div class="lab">{range_lab}</div><div class="rate" title="Source: FRED DFEDTARL / DFEDTARU">{rng}</div>'
                    f'<span class="chip {cls}" title="Change from the previous meeting, in percentage points">{chip}</span></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="fact"><div class="lab">{vote_lab}</div>{vote}</div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="fact tone"><div class="lab">Tone</div>{stripe}'
                    f'<div class="tcap {tcls}" title="Source: decoder card score {card.tone_score:+.1f} on a −2 to +2 scale">{tcap}</div></div>',
                    unsafe_allow_html=True)
        if nx:
            arrow = {"hike": "▲", "cut": "▼", "hold": "→"}[nx[1]]
            with c4:
                st.markdown('<div class="fact"><div class="lab">Next</div></div>', unsafe_allow_html=True)
                with st.container(key="nextchip"):
                    if st.button(f"{arrow}\u00a0{ui.short_move(nx[1], nx[2])}".replace(" ", "\u00a0") + f", {pd.Timestamp(nx[0]):%b\u00a0%-d}\u00a0→", key="next_btn",
                                 help=f"What the Fed did at the following meeting, {long_date(nx[0])}"):
                        open_meeting(nx[0])
                        st.rerun()


# ---------------------------------------------------------------- the four answers
TOPICS = [
    ("inflation", re.compile(r"inflation|price", re.I), "CPIAUCSL", True, "Inflation"),
    ("jobs", re.compile(r"job|employment|unemployment|labor", re.I), "UNRATE", False, "Unemployment"),
    ("growth", re.compile(r"activity|growth|spending|output|investment|productivity", re.I), "GDPC1", True, "Growth"),
]


def reasons(card, ctx) -> list[dict]:
    when = pd.Timestamp.today() if ctx["meeting_date"] == "pasted" else pd.Timestamp(ctx["meeting_date"])
    out = []
    for q in card.tone_quotes[:3]:
        topic = next((t for t in TOPICS if t[1].search(q.quote)), None)
        item = {"quote": q.quote, "dir": q.direction, "topic": topic[0] if topic else None}
        if topic:
            _, _, sid, yoy, label = topic
            if sid == "GDPC1":
                v = store.gdp_growth_asof(when)
                series = spark_series(sid, 12, True, when - pd.Timedelta(days=95))
            elif yoy:
                v = store.yoy_asof(sid, when)
                series = spark_series(sid, 24, True, when - pd.Timedelta(days=35))
            else:
                v = store.value_asof(sid, when)
                series = spark_series(sid, 24, False, when - pd.Timedelta(days=35))
            if v:
                item.update({"label": label, "value": v[1], "asof": v[0], "sid": sid, "series": series})
        out.append(item)
    return out


def why_sentence(rs: list[dict]) -> str:
    for r in rs:
        if r.get("value") is not None:
            src = f'title="Source: FRED {r["sid"]}, {r["asof"]:%b %Y}"'
            if r["topic"] == "inflation":
                return f'Inflation <span class="mono" {src}>{r["value"]:.1f}%</span>, goal <span class="mono">2%</span>.'
            if r["topic"] == "jobs":
                return f'Unemployment <span class="mono" {src}>{r["value"]:.1f}%</span>.'
            if r["topic"] == "growth":
                return f'Growth <span class="mono" {src}>{r["value"]:+.1f}%</span> a year.'
    return ui.E(ui.plain(rs[0]["quote"], 8)) if rs else "No reason stated."


def is_decision_or_vote(sentence: str) -> bool:
    s = sentence.lower()
    decision = (("target range for the federal funds rate" in s or "target for the federal funds rate" in s)
                and re.search(r"decided|maintain|raise|lower|keep|reduce|increase", s) is not None)
    return decision or s.startswith(("voting", "absent")) or "approved the following statement" in s


PILLS = ["Credit card", "Savings", "Car loan", "Fixed mortgage", "Adjustable mortgage", "Job hunting"]


def my_items(ctx, bps: int) -> list[dict]:
    when = pd.Timestamp.today() if ctx["meeting_date"] == "pasted" else pd.Timestamp(ctx["meeting_date"])
    out = []
    mine = ss.mine
    hold = bps == 0
    sens = 25  # on a hold, show what one quarter-point move would do
    if "Credit card" in mine:
        apr = store.value_asof("TERMCBCCALLNS", when)
        if apr:
            r = impact.payment_impact("credit_card", 5000, bps if not hold else sens, apr[1])
            out.append({"k": f"Card APR ~{apr[1]:.1f}%", "v": "unchanged" if hold else ui.signed_money(r.annual_change, "/yr"),
                        "s": (f"A ¼-pt hike next: {ui.signed_money(r.annual_change, '/yr')} on a $5,000 balance" if hold else "On a $5,000 balance carried month to month"),
                        "amt": 0 if hold else r.annual_change, "src": f"FRED TERMCBCCALLNS, {apr[0]:%b %Y}"})
    if "Savings" in mine:
        r = impact.savings_impact(10000, bps if not hold else -sens)
        out.append({"k": "High-yield savings", "v": "unchanged" if hold else ui.signed_money(r["annual_change"], "/yr"),
                    "s": (f"A ¼-pt cut next: {ui.signed_money(r['annual_change'], '/yr')} on $10,000" if hold else "Interest on $10,000; banks pass on about 60%"),
                    "amt": 0 if hold else -r["annual_change"], "src": "Pass-through assumption of 60%"})
    if "Car loan" in mine:
        rate = store.value_asof("RIFLPBCIANM60NM", when)
        if rate:
            move = round((bps if not hold else sens) * impact.PASS_THROUGH["auto_60m"])
            r = impact.payment_impact("auto_60m", 30000, move, rate[1])
            out.append({"k": f"New car loan ~{rate[1]:.1f}%", "v": "unchanged" if hold else ui.signed_money(r.monthly_change),
                        "s": (f"A ¼-pt hike next: {ui.signed_money(r.monthly_change)} on $30,000 over 60 months" if hold
                              else "$30,000 over 60 months; car loans move about half as much"),
                        "amt": 0 if hold else r.monthly_change * 12, "src": f"FRED RIFLPBCIANM60NM, {rate[0]:%b %Y}"})
    if "Fixed mortgage" in mine:
        out.append({"k": "Fixed mortgage", "v": "unchanged", "s": "Your payment is locked. New mortgages follow the 10-yr Treasury.", "amt": 0, "src": "Fixed rate"})
    if "Adjustable mortgage" in mine:
        m = store.value_asof("MORTGAGE30US", when)
        if m:
            r = impact.payment_impact("mortgage_30y", 300000, bps if not hold else sens, m[1] - 0.5)
            out.append({"k": "Adjustable mortgage", "v": "unchanged" if hold else ui.signed_money(r.monthly_change),
                        "s": (f"A ¼-pt hike next: {ui.signed_money(r.monthly_change)} at reset on $300,000" if hold else "At your next reset, on $300,000"),
                        "amt": 0 if hold else r.monthly_change * 12, "src": f"FRED MORTGAGE30US, {m[0]:%b %Y}"})
    if "Job hunting" in mine:
        ur = store.value_asof("UNRATE", when)
        pay = store.payroll_avg_change(when)
        if ur:
            out.append({"k": "Unemployment", "v": f"{ur[1]:.1f}%", "s": (f"Employers added {pay[1]:+,.0f}k jobs a month over 3 months" if pay else ""),
                        "amt": 0, "src": f"FRED UNRATE / PAYEMS, {ur[0]:%b %Y}"})
    return out


def sync_profile() -> None:
    """Map the pills to a Profile (typical amounts) so the AI's my_impact tool can show the reader's numbers."""
    m = ss.mine
    if not m:
        ss.pop("profile", None)
        return
    housing = "arm" if "Adjustable mortgage" in m else "fixed" if "Fixed mortgage" in m else "rent"
    ss.profile = personal.Profile(housing=housing, mortgage_balance=300000.0 if housing == "arm" else 0.0,
                                  card_balance=5000.0 if "Credit card" in m else 0.0, car_loan="shopping" if "Car loan" in m else "none",
                                  car_amount=30000.0 if "Car loan" in m else 0.0, savings=10000.0 if "Savings" in m else 0.0)


def you_sentence(items: list[dict], bps: int) -> str:
    if not ss.mine:
        return "Pick yours."
    if bps == 0:
        return "Nothing changes for you this month."
    moving = [i for i in items if abs(i.get("amt", 0)) >= 0.005]
    if not moving:
        return "Nothing you picked moves with this."
    top = max(moving, key=lambda i: abs(i["amt"]))
    name = ui.E(top["k"].split(" ~")[0])
    return f'{name}: <span class="mono" title="Source: {ui.E(top["src"])}">{ui.E(top["v"])}</span>.'


def card_shell(cid: str, title: str, sentence_html: str, visual_html: str, body) -> None:
    is_open = ss.open_card == cid
    with st.container(key=f"card{'open' if is_open else ''}_{cid}"):
        with st.container(key=f"cardh_{cid}"):
            tog = "−" if is_open else "+"
            st.markdown(f'<div class="ctitle"><span>{title}</span><span class="tog">{tog}</span></div>'
                        f'<div class="csent">{sentence_html}</div>{visual_html}', unsafe_allow_html=True)
            with st.container(key=f"hit_{cid}"):
                if st.button(f"{'Close' if is_open else 'Open'} {title}", key=f"hitb_{cid}"):
                    ss.open_card = None if is_open else cid
                    st.rerun()
        if is_open:
            st.markdown('<div class="cbody"></div>', unsafe_allow_html=True)
            body()


def answers(card, ctx, is_latest: bool) -> None:
    d = card.decision
    rs = reasons(card, ctx)

    def why_body():
        for r in rs:
            spk = ""
            if r.get("series"):
                col = theme.HIKE if r["dir"] == "hawkish" else theme.CUT if r["dir"] == "dovish" else theme.INK
                spk = (f'<div class="spk">{ui.sparkline(r["series"], 120, 30, col)}<br>{r["label"]} '
                       f'<span title="Source: FRED {r["sid"]}, {r["asof"]:%b %Y}">{r["value"]:.1f}%</span></div>')
            arrow = "▲ hawkish" if r["dir"] == "hawkish" else "▼ dovish" if r["dir"] == "dovish" else "neutral"
            st.markdown(f'<div class="reason"><div><p>“{ui.E(r["quote"])}”</p><span class="mini">{arrow}</span></div>{spk}</div>', unsafe_allow_html=True)

    items = ui.changed_sentences(ctx.get("prev_statement"), ctx["statement"], card.changes, skip=is_decision_or_vote)

    def changed_body():
        for it in items:
            note = f'<div class="note">{ui.E(ui.plain(it["note"], 10))}</div>' if it["note"] else ""
            st.markdown(f'<div class="chg"><p>{ui.redline_html(it)}</p>{note}</div>', unsafe_allow_html=True)
        with st.expander("Show full statement"):
            st.markdown('<div class="redline">' + "".join(f"<p>{ui.E(p)}</p>" for p in ctx["statement"].split("\n\n")) + "</div>", unsafe_allow_html=True)

    if items:
        swap = next((ui.swap_phrase(i) for i in items if ui.swap_phrase(i)), None)
        csent = f'<span class="mono">{len(items)}</span> change{"s" if len(items) != 1 else ""}' + (f" · {swap}" if swap else "")
    else:
        csent = "Same wording as last time." if ctx.get("prev_statement") else "First statement on record."
    frac = ctx.get("changed_fraction") or 0
    cvis = ""
    if ctx.get("prev_statement"):
        cvis = (f'<div class="sbar" style="max-width:160px" title="{frac * 100:.0f}% of words changed vs. {short_date(ctx["prev_meeting_date"])}">'
                f'<i style="width:{max(frac * 100, 2):.0f}%;background:{theme.INK}"></i><i style="flex:1;background:{theme.RULE}"></i></div>')

    mi = my_items(ctx, int(d.change_bps))

    def you_body():
        with st.container(key="mypills"):
            sel = st.pills("What do you have?", PILLS, selection_mode="multi", default=ss.mine, key="pills_w", label_visibility="collapsed")
        if sorted(sel or []) != sorted(ss.mine):
            ss.mine = list(sel or [])
            sync_profile()
            st.rerun()
        if mi:
            st.markdown("".join(f'<div class="mine"><span class="k">{ui.E(i["k"])}</span><span class="v" title="Source: {ui.E(i["src"])}">{ui.E(i["v"])}</span>'
                                f'<span class="s">{ui.E(i["s"])}</span></div>' for i in mi), unsafe_allow_html=True)

    if is_latest:
        f = cached_forecast()
        p = {"hold": f["p_hold"], "cut": f["p_cut"], "hike": f["p_hike"]}
        conf = f["confidence"]
    elif ctx.get("forecast"):
        p = {k: ctx["forecast"][k] / 100 for k in ("hold", "cut", "hike")}
        conf = None
    else:
        p, conf = None, None
    if p:
        top = max(p, key=p.get)
        nsent = f'<span class="mono">{p[top] * 100:.0f}%</span> {top}' + (f" · {conf} confidence" if conf else " expected then")
        nvis = ui.stacked_odds(p)
    else:
        nsent, nvis = "No forecast for this one.", ""

    def next_body():
        bt = forecast_mod.backtest_summary() if forecast_mod.BACKTEST_PATH.exists() else {}
        key = ctx["meeting_date"]
        sep = taylor = mid = trend = None
        if is_latest:
            s = cached_forecast()["signals"]
            sep, taylor, mid, trend = s["sep_median"], s["taylor_rate"], s["current_mid"], s["tone_trend"]
        elif key in features().index:
            r = features().loc[key]
            sep = None if pd.isna(r["sep_median"]) else float(r["sep_median"])
            taylor = None if pd.isna(r["taylor_rate"]) else float(r["taylor_rate"])
            mid, trend = float(r["mid"]), float(r["tone_trend"])
        rows = []
        if sep is not None:
            rows.append((f"Officials’ projection ({ui.term('SEP')})", f"{sep:.2f}%", "FRED FEDTARMD vintage"))
        if taylor is not None:
            rows.append((ui.term("Taylor rule"), f"{taylor:.2f}%", "Taylor (1993) with core PCE and the CBO output gap"))
        if mid is not None:
            rows.append(("Current midpoint", f"{mid:.3f}%", "FRED DFEDTARL / DFEDTARU"))
        if trend is not None:
            rows.append(("Tone trend", f"{trend:+.2f}", "Tone vs the average of the previous 3 statements"))
        html = "".join(f'<div class="sig"><span>{k}</span><span class="v" title="Source: {ui.E(src)}">{ui.E(v)}</span></div>' for k, v, src in rows)
        if bt:
            html += (f'<p class="mini" style="margin-top:10px">Backtest: right <span class="mono">{bt["model_hit_rate"] * 100:.0f}%</span> of '
                     f'{bt["n"]} meetings vs <span class="mono">{bt["baseline_hit_rate"] * 100:.0f}%</span> for always guessing “no change”. '
                     "Educational, not financial advice.</p>")
        st.markdown(html, unsafe_allow_html=True)

    why_vis = ui.sparkline(rs[0]["series"], 120, 28) if rs and rs[0].get("series") else ""
    st.markdown('<div class="band"></div>', unsafe_allow_html=True)
    row1 = st.columns(2, gap="medium")
    with row1[0]:
        card_shell("why", "Why", why_sentence(rs), why_vis, why_body)
    with row1[1]:
        card_shell("changed", "What changed", csent, cvis, changed_body)
    row2 = st.columns(2, gap="medium")
    with row2[0]:
        card_shell("you", "For you", you_sentence(mi, int(d.change_bps)), "", you_body)
    with row2[1]:
        card_shell("next", "What’s next", nsent, nvis, next_body)


# ---------------------------------------------------------------- AI answers as working results
def meeting_row(d: str, key: str) -> None:
    g = meetings().set_index(meetings()["meeting_date"].dt.strftime("%Y-%m-%d")).loc[d]
    gt = store.ground_truth().set_index("meeting_date").loc[pd.Timestamp(d)]
    vote = "" if pd.isna(gt["votes_for"]) else f" · {int(gt['votes_for'])}–{int(gt['votes_against'])}"
    arrow, cls = ui.arrow_chip(g["direction"], int(g["change_bps"]))
    c1, c2 = st.columns([4, 1], vertical_alignment="center")
    c1.markdown(f'<div class="res-row"><span class="res-date">{short_date(d)}</span><span class="res-move {cls}">{arrow}</span>'
                f'<span class="sub">{ui.fmt_range(g["target_low"], g["target_high"])}{vote}</span></div>', unsafe_allow_html=True)
    if c2.button("Open →", type="tertiary", key=key):
        open_meeting(d)
        st.rerun()


def render_results(calls: list[dict], key: str) -> None:
    """Show what the AI's tools returned (meetings, payments, series, odds) instead of more prose."""
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
                    meeting_row(str(d.date()), k)
            elif name == "notable_meetings":
                for j, m in enumerate(T.notable_meetings(args.get("kind", "split"), int(args.get("limit", 5)))["meetings"][:5]):
                    meeting_row(m["meeting_date"], f"{k}_{j}")
            elif name == "payment_impact":
                r = T.payment_impact(**{a: args[a] for a in ("loan_type", "balance", "rate_change_bps", "base_rate_pct") if a in args})
                if "error" not in r:
                    label = {"mortgage_30y": "30-year mortgage", "auto_60m": "Car loan", "credit_card": "Credit card", "heloc": "Home equity line"}.get(r["loan_type"], r["loan_type"])
                    st.markdown(f'<div class="tilebox"><div class="lab">{label}, ${r["balance"]:,.0f} at {r["base_rate_pct"]:.2f}%</div>'
                                f'<div class="big">{ui.signed_money(r["monthly_change"])}</div>'
                                f'<div class="cap">${r["monthly_before"]:,.2f} → ${r["monthly_after"]:,.2f} a month</div></div>', unsafe_allow_html=True)
            elif name == "my_impact" and ss.get("profile"):
                bps = int(args.get("rate_change_bps", 25))
                r = personal.personal_impact(ss.profile, bps, 0, pd.Timestamp.today())
                kind = "cut" if bps < 0 else "hike"
                st.markdown(f'<div class="tilebox"><div class="lab">You, after a {kind} of {abs(bps)} bp</div>'
                            f'<div class="big">{ui.signed_money(r.monthly_total)}</div><div class="cap">typical amounts for what you picked</div></div>',
                            unsafe_allow_html=True)
            elif name == "get_series":
                r = T.get_series(**{a: args[a] for a in ("id", "start", "end") if a in args})
                if "error" not in r and r.get("points"):
                    ys = [p["value"] for p in r["points"]]
                    st.markdown(f'<div class="tilebox"><div class="lab">{ui.E(r["description"])} · FRED {ui.E(r["series_id"])}</div>'
                                f'{ui.sparkline(ys, 400, 70)}<div class="cap">{r["first"]["date"]}: {r["first"]["value"]} → '
                                f'{r["last"]["date"]}: {r["last"]["value"]}</div></div>', unsafe_allow_html=True)
            elif name == "forecast_next":
                f = cached_forecast()
                odds = ui.stacked_odds({"hold": f["p_hold"], "cut": f["p_cut"], "hike": f["p_hike"]})
                st.markdown(f'<div class="tilebox"><div class="lab">Next meeting</div>{odds}</div>', unsafe_allow_html=True)
            elif name == "diff_statements":
                r = T.diff_statements(str(args.get("a", "")), str(args.get("b", "")))
                if "error" not in r:
                    rows = []
                    for x in r["changes"][:3]:
                        old = "<del>" + ui.E(x["old"]) + "</del> " if x["old"] else ""
                        new = "<ins>" + ui.E(x["new"]) + "</ins>" if x["new"] else ""
                        rows.append(f"<p>{old}{new}</p>")
                    st.markdown('<div class="redline">' + "".join(rows) + "</div>", unsafe_allow_html=True)
            elif name == "search_statements":
                for hit in T.search_statements(str(args.get("query", "")))["results"][:3]:
                    more = "…" if len(hit["text"]) > 240 else ""
                    st.markdown(f'<div class="res-quote"><span class="res-date">{short_date(hit["meeting_date"])}</span>'
                                f'<p>“{ui.E(hit["text"][:240])}{more}”</p></div>', unsafe_allow_html=True)
            elif name == "fed_leadership":
                r = T.fed_leadership()
                if "error" not in r:
                    people = "".join(f'<div><strong>{ui.E(m["name"])}</strong><span>{ui.E(m["title"])}</span></div>' for m in r["members"])
                    st.markdown(f'<div class="res-people">{people}</div>', unsafe_allow_html=True)
        except Exception:
            continue


@st.dialog("Answer", width="large")
def answer_panel() -> None:
    a = ss.get("answer")
    if not a:
        return
    st.markdown(f'<div class="aq">{ui.E(a["q"])}</div>', unsafe_allow_html=True)
    st.markdown(a["text"])  # Markdown from the model; HTML is not allowed here
    render_results(a.get("calls", []), "ans")


REFERS_TO_MEETING = re.compile(r"\b(this|that|it|they|the decision|dissent\w*|vote\w*|why|change\w*|wording|statement)\b", re.I)


def handle_ask(text: str) -> None:
    target, extra = interpret(text)
    if target == "pasted":
        ss.pasted, ss.pasted_label = text, None
        open_meeting("pasted")
        st.rerun()
    if target is None:
        ss.answer = {"q": text, "text": extra or "Try a question, or a meeting like “September 2024”.", "calls": []}
        answer_panel()
        return
    if target != "question":
        open_meeting(target)
        if not extra:
            st.rerun()
        text = extra
    if config.SESSION_QUESTION_LIMIT - ss.questions <= 0:
        ss.answer = {"q": text, "text": "That’s the question limit for this visit.", "calls": []}
        answer_panel()
        return
    ss.questions += 1
    if target != "question":
        meeting = target
    else:
        viewing = None if ss.meeting == "pasted" else current()
        meeting = viewing if (viewing and REFERS_TO_MEETING.search(text)) else None
    reader = personal.ai_labels(ss.profile) if ss.get("profile") and ss.get("ai_tailor") else None
    with st.spinner(""):
        try:
            ans = agent.answer(text, meeting=meeting, reader=reader, has_profile=bool(ss.get("profile")))
        except Exception:
            ans = agent.rules_answer(text, meeting=meeting)
    ss.answer = {"q": text, "text": ans.text, "calls": ans.tool_calls}
    answer_panel()


def suggested(card) -> list[str]:
    if card is None:
        return ["What is the Fed?", "Who is the Fed chair?", "What happened at the last meeting?"]
    d = card.decision
    qs = []
    if d.dissenters:
        qs.append(f"Why did {' and '.join(n.split()[-1] for n in d.dissenters[:2])} dissent?")
    qs.append({"hold": "Why hold?", "cut": "Why cut?", "hike": "Why raise?"}[d.direction])
    qs.append("What would a ¼-pt hike mean for me?" if ss.get("profile") else "Who is the Fed chair?")
    return qs[:3]


def ask_bar(card) -> None:
    """Slim bar fixed to the bottom of the viewport. A plain form (not st.chat_input) so the page doesn't
    auto-scroll to the bottom; suggested questions appear when the bar is focused or hovered."""
    chips = suggested(card)
    picked = None
    with st.bottom:
        with st.container(key="askchips"):
            cols = st.columns(len(chips))
            for i, q in enumerate(chips):
                if cols[i].button(q, key=f"chip_{i}"):
                    picked = q
        with st.form("askbar", border=False, clear_on_submit=True):
            c1, c2 = st.columns([12, 1], vertical_alignment="bottom", gap="small")
            typed = c1.text_input("Ask", placeholder="Ask about this meeting…", label_visibility="collapsed")
            sent = c2.form_submit_button("↑", type="primary", use_container_width=True)
    q = picked or (typed.strip() if sent and typed and typed.strip() else None)
    if q:
        handle_ask(q)


# ---------------------------------------------------------------- pages
def meeting_page():
    if ss.meeting == "pasted":
        ctx = build_context_pasted(ss.get("pasted", ""))
        card = ss.get("pasted_card")
        if card is None or ss.get("pasted_card_for") != ss.get("pasted"):
            card = None
            if not agent.near_cap():
                with st.spinner(""):
                    try:
                        card = build_llm_card(ctx)
                    except Exception:
                        card = None
            card = card or build_rules_card(ctx)
            ss.pasted_card, ss.pasted_card_for = card, ss.get("pasted")
        is_latest = False
    else:
        d = current()
        ctx = cached_context(d)
        card = load_card(d) or build_rules_card(ctx)
        is_latest = d == dates()[-1]
    verdict(card, ctx)
    answers(card, ctx, is_latest)
    return card


def about_page() -> None:
    rows = [
        ("Where the data comes from", f"Every Fed decision since 2000 ({len(dates())} statements). Figures come straight from the Federal Reserve "
                                      "and FRED, calculated in code."),
        ("The AI", "The Gemini API (Groq as backup) drafts the explanations. Every number and quote is checked."),
        ("Your privacy", "Nothing you enter is saved. Your choices are used only during your visit, and your amounts never go to an AI."),
    ]
    st.markdown('<div class="verdict"><h1>About</h1></div>' + "".join(f'<div class="about-row"><h3>{k}</h3><p>{ui.E(v)}</p></div>' for k, v in rows)
                + '<p class="byline">Built by Keith LoboPrabhu</p>', unsafe_allow_html=True)


# Shareable links: ?m=YYYY-MM-DD opens that meeting; the address follows the reader.
qp = st.query_params.get("m")
if qp and qp != ss.get("_qp") and qp in dates():
    ss._qp = qp
    open_meeting(qp)

top_bar()
if ss.page == "meeting" and current() == dates()[-1] and ss.meeting != "pasted":
    live_strip()
stair()
card = None
if ss.page == "about":
    about_page()
else:
    card = meeting_page()
st.markdown(ui.footer_html("Not financial advice. Data: Federal Reserve, FRED."), unsafe_allow_html=True)
if ss.page == "meeting" and ss.meeting not in (None, "pasted"):
    if st.query_params.get("m") != ss.meeting:
        st.query_params["m"] = ss._qp = ss.meeting
elif "m" in st.query_params and (ss.meeting is None):
    del st.query_params["m"]
ask_bar(card)
