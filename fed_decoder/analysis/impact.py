"""Household impact math. Every number shown in "For you" comes from here."""
from __future__ import annotations

from dataclasses import asdict, dataclass

LOAN_TERMS_MONTHS = {
    "mortgage_30y": 360,
    "auto_60m": 60,
    "heloc": 120,  # interest-only draw period approximated as 10y amortization
}
REVOLVING = {"credit_card"}

# How much of a fed funds move typically passes through, by product.
# Credit cards and HELOCs are priced off prime (= fed funds upper + 3%), so ~1:1.
# Auto loans pass through partially; 30y mortgages follow the 10-year Treasury.
PASS_THROUGH = {"credit_card": 1.0, "heloc": 1.0, "auto_60m": 0.5, "mortgage_30y": 0.0, "savings": 0.6}


def monthly_payment(principal: float, annual_rate_pct: float, months: int) -> float:
    """Standard amortization: P * r / (1 - (1 + r)^-n)."""
    if months <= 0:
        raise ValueError("months must be positive")
    r = annual_rate_pct / 100.0 / 12.0
    if abs(r) < 1e-12:
        return principal / months
    return principal * r / (1.0 - (1.0 + r) ** (-months))


@dataclass
class PaymentImpact:
    loan_type: str
    balance: float
    base_rate_pct: float
    new_rate_pct: float
    rate_change_bps: int
    monthly_before: float
    monthly_after: float
    monthly_change: float
    annual_change: float
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


def payment_impact(loan_type: str, balance: float, rate_change_bps: int, base_rate_pct: float) -> PaymentImpact:
    """Change in monthly payment if the loan's rate moves by `rate_change_bps`.

    For a revolving balance (credit card) the change is the interest-only
    difference: balance * delta_rate / 12.
    """
    new_rate = base_rate_pct + rate_change_bps / 100.0
    if loan_type in REVOLVING:
        before = balance * base_rate_pct / 100 / 12
        after = balance * new_rate / 100 / 12
        note = "Card APRs are set off the prime rate, which moves with the fed funds rate."
    elif loan_type in LOAN_TERMS_MONTHS:
        n = LOAN_TERMS_MONTHS[loan_type]
        before = monthly_payment(balance, base_rate_pct, n)
        after = monthly_payment(balance, new_rate, n)
        note = {
            "mortgage_30y": "30-year mortgage rates track the 10-year Treasury yield, not the fed funds rate directly.",
            "auto_60m": "Auto loan rates move partly with the Fed; fixed-rate loans you already have do not change.",
            "heloc": "HELOC rates are usually prime plus a margin, so they follow the Fed closely.",
        }[loan_type]
    else:
        raise ValueError(f"unknown loan_type {loan_type!r}; use one of {sorted(LOAN_TERMS_MONTHS) + sorted(REVOLVING)}")
    return PaymentImpact(
        loan_type=loan_type,
        balance=round(balance, 2),
        base_rate_pct=round(base_rate_pct, 3),
        new_rate_pct=round(new_rate, 3),
        rate_change_bps=int(rate_change_bps),
        monthly_before=round(before, 2),
        monthly_after=round(after, 2),
        monthly_change=round(after - before, 2),
        annual_change=round((after - before) * 12, 2),
        note=note,
    )


def savings_impact(balance: float, rate_change_bps: int, pass_through: float = PASS_THROUGH["savings"]) -> dict:
    """Change in annual interest on a high-yield savings balance."""
    delta = balance * (rate_change_bps / 10000.0) * pass_through
    return {"balance": balance, "rate_change_bps": rate_change_bps, "pass_through": pass_through, "annual_change": round(delta, 2)}
