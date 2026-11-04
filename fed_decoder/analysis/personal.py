"""Personal "For you" impact, computed in code only.

Privacy: a Profile is never sent to an LLM, written to disk, logged, or
cached. It lives in the viewer's Streamlit session and is gone when the tab
closes. Gender is deliberately not collected: no Fed effect computed here
depends on it.

Pass-through assumptions (how much of a fed funds move reaches each product):
  credit cards, HELOCs, variable private student loans: ~1:1 (priced off prime)
  adjustable-rate mortgage: ~1:1 at the next reset (indexes follow short rates)
  new 30-year fixed mortgage: follows the 10-year Treasury, not fed funds
  new auto loan: ~0.5
  high-yield savings: ~0.6; ordinary checking/savings: ~0
  existing fixed-rate mortgage, car loan, federal student loans: no change
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from fed_decoder import config
from fed_decoder.analysis import impact

HOUSING = {
    "rent": "I rent",
    "fixed": "I own, fixed-rate mortgage",
    "arm": "I own, adjustable-rate mortgage",
    "outright": "I own outright",
    "buying": "I'm planning to buy a home",
}
INCOME = {  # label -> annual midpoint used only to express costs as a share of income
    "Prefer not to say": None,
    "Under $30k": 22_500,
    "$30k–$60k": 45_000,
    "$60k–$100k": 80_000,
    "$100k–$150k": 125_000,
    "$150k–$250k": 200_000,
    "Over $250k": 300_000,
}
SAVINGS_KIND = {"high_yield": "High-yield savings or money market", "bank": "Regular bank savings/checking"}


@dataclass
class Profile:
    housing: str = "rent"
    mortgage_balance: float = 0.0      # ARM balance, or planned loan size if buying
    heloc_balance: float = 0.0
    card_balance: float = 0.0          # balance carried month to month
    car_loan: str = "none"             # none | have_fixed | shopping
    car_amount: float = 0.0
    private_student_variable: float = 0.0
    savings: float = 0.0
    savings_kind: str = "high_yield"
    income: str = "Prefer not to say"
    state: str | None = None


@dataclass
class PersonalImpact:
    items: list[dict] = field(default_factory=list)   # {topic, number, text, monthly}
    monthly_total: float = 0.0
    share_of_income: float | None = None
    per_25bp_monthly: float = 0.0                      # sensitivity to a 25 bp move
    notes: list[str] = field(default_factory=list)


def _usd(x: float) -> str:
    return f"${abs(x):,.2f}"


def _bal(x: float) -> str:
    return f"${x:,.0f}"


def _signed(x: float) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "") + _usd(x)


def _latest(sid: str, when: pd.Timestamp) -> float | None:
    from fed_decoder.data import store

    v = store.value_asof(sid, when)
    return v[1] if v else None


def state_unemployment(code: str, when: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    try:
        df = pd.read_parquet(config.STATE_UR_PATH)
    except Exception:
        return None
    df = df[(df["state"] == code) & (pd.to_datetime(df["date"]) <= pd.Timestamp(when) - pd.Timedelta(days=35))]
    if df.empty:
        return None
    r = df.sort_values("date").iloc[-1]
    return pd.Timestamp(r["date"]), float(r["value"])


def _monthly_changes(p: Profile, bps: int, ten_year_bps: int, when: pd.Timestamp) -> list[dict]:
    """One item per product the person has; `monthly` is the signed $ change."""
    items: list[dict] = []
    prime = (_latest("DFEDTARU", when) or 5.0) + 3.0

    if p.card_balance > 0:
        apr = _latest("TERMCBCCALLNS", when) or 21.0
        r = impact.payment_impact("credit_card", p.card_balance, bps, apr)
        items.append({"topic": "Credit card", "monthly": r.monthly_change,
                      "text": f"Interest on your {_bal(p.card_balance)} balance at about {apr:.2f}% APR moves with the Fed almost one for one."})

    if p.housing == "fixed":
        items.append({"topic": "Mortgage", "monthly": 0.0,
                      "text": "Your fixed-rate mortgage payment does not change. Fed moves only matter if you refinance or sell."})
    elif p.housing == "arm" and p.mortgage_balance > 0:
        rate = (_latest("MORTGAGE30US", when) or 6.5) - 0.5
        r = impact.payment_impact("mortgage_30y", p.mortgage_balance, bps, rate)
        items.append({"topic": "Adjustable mortgage", "monthly": r.monthly_change,
                      "text": f"At your next reset, a {_bal(p.mortgage_balance)} adjustable loan would likely move with short-term rates (estimate assumes about {rate:.2f}% today)."})
    elif p.housing == "buying" and p.mortgage_balance > 0:
        rate = _latest("MORTGAGE30US", when) or 6.5
        r = impact.payment_impact("mortgage_30y", p.mortgage_balance, ten_year_bps, rate)
        items.append({"topic": "Home you're buying", "monthly": r.monthly_change,
                      "text": f"New 30-year mortgages follow the 10-year Treasury, not the Fed. It moved {ten_year_bps:+d} bp on the day; on a {_bal(p.mortgage_balance)} loan at {rate:.2f}% that changes the payment as shown."})
    elif p.housing == "rent":
        items.append({"topic": "Rent", "monthly": 0.0,
                      "text": "Rent isn't tied to the Fed directly. Higher rates can slow building and home buying, which affects rents slowly and indirectly."})

    if p.heloc_balance > 0:
        r = impact.payment_impact("heloc", p.heloc_balance, bps, prime + 0.5)
        items.append({"topic": "Home equity line", "monthly": r.monthly_change,
                      "text": f"HELOCs are priced off the prime rate (about {prime:.2f}% now), so your {_bal(p.heloc_balance)} line follows the Fed closely."})

    if p.car_loan == "have_fixed":
        items.append({"topic": "Car loan", "monthly": 0.0, "text": "Your existing fixed-rate car loan does not change."})
    elif p.car_loan == "shopping" and p.car_amount > 0:
        rate = _latest("RIFLPBCIANM60NM", when) or 7.5
        move = round(bps * impact.PASS_THROUGH["auto_60m"])
        r = impact.payment_impact("auto_60m", p.car_amount, move, rate)
        items.append({"topic": "Car you're buying", "monthly": r.monthly_change,
                      "text": f"New car loans move about half as much as the Fed; on {_bal(p.car_amount)} over 60 months at about {rate:.2f}%."})

    if p.private_student_variable > 0:
        r = impact.payment_impact("heloc", p.private_student_variable, bps, prime)  # 10-year amortization
        items.append({"topic": "Private student loan", "monthly": r.monthly_change,
                      "text": f"Variable-rate private student loans follow short-term rates; estimate for {_bal(p.private_student_variable)} over 10 years. Federal student loans are fixed and don't change."})

    if p.savings > 0:
        pt = impact.PASS_THROUGH["savings"] if p.savings_kind == "high_yield" else 0.0
        annual = impact.savings_impact(p.savings, bps, pt)["annual_change"]
        # savings interest is income: a higher rate is a positive for you, so flip the sign for "cost"
        items.append({"topic": "Savings", "monthly": -round(annual / 12, 2),
                      "text": (f"High-yield accounts pass on about {pt:.0%} of Fed moves: {_signed(annual)} a year in interest on {_bal(p.savings)}."
                               if pt else "Regular bank accounts barely change their rates when the Fed moves.")})
    return items


def personal_impact(p: Profile, change_bps: int, ten_year_move_bps: int | None, when) -> PersonalImpact:
    when = pd.Timestamp(when)
    ten = int(ten_year_move_bps or 0)
    items = _monthly_changes(p, int(change_bps), ten, when)
    for it in items:
        m = it["monthly"]
        it["number"] = "no change" if abs(m) < 0.005 else (f"{_signed(m)}/mo" if it["topic"] != "Savings" else f"{_signed(-m)}/mo")
    total = round(sum(it["monthly"] for it in items), 2)
    # Sensitivity: what every 25 bp Fed move means for this person (mortgage-for-purchase excluded: it follows the 10-year).
    sens = sum(it["monthly"] for it in _monthly_changes(p, 25, 0, when) if it["topic"] != "Home you're buying")
    out = PersonalImpact(items=items, monthly_total=total, per_25bp_monthly=round(sens, 2))
    inc = INCOME.get(p.income)
    if inc:
        out.share_of_income = round(total / (inc / 12) * 100, 2)
    if p.state:
        su = state_unemployment(p.state, when)
        nat = _latest("UNRATE", when)
        if su:
            cmp = "" if nat is None else (f", {'above' if su[1] > nat else 'below' if su[1] < nat else 'equal to'} the national {nat:.1f}%")
            out.items.append({"topic": "Jobs where you live", "monthly": 0.0, "number": f"{su[1]:.1f}%",
                              "text": f"Unemployment in {config.STATES[p.state]} was {su[1]:.1f}% in {su[0]:%B %Y}{cmp}. Rate hikes cool hiring with a lag; cuts aim to support it."})
    return out
