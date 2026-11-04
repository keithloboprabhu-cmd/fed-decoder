import ast
from pathlib import Path

from fed_decoder.analysis import impact
from fed_decoder.analysis.personal import Profile, personal_impact


def by_topic(r):
    return {i["topic"]: i for i in r.items}


def test_fixed_mortgage_and_rent_do_not_change():
    r = personal_impact(Profile(housing="fixed"), -50, -10, "2024-09-18")
    assert by_topic(r)["Mortgage"]["monthly"] == 0.0
    r = personal_impact(Profile(housing="rent"), 75, 20, "2022-06-15")
    assert by_topic(r)["Rent"]["monthly"] == 0.0 and r.monthly_total == 0.0


def test_card_matches_impact_math():
    r = personal_impact(Profile(housing="rent", card_balance=6000), 25, 0, "2023-07-26")
    expect = round(6000 * 0.0025 / 12, 2)
    assert by_topic(r)["Credit card"]["monthly"] == expect


def test_home_purchase_follows_10_year_not_fed():
    r = personal_impact(Profile(housing="buying", mortgage_balance=400_000), -50, 0, "2024-09-18")
    assert by_topic(r)["Home you're buying"]["monthly"] == 0.0  # 10-year didn't move
    r = personal_impact(Profile(housing="buying", mortgage_balance=400_000), 0, 20, "2024-09-18")
    assert by_topic(r)["Home you're buying"]["monthly"] > 0


def test_savings_sign_and_bank_accounts():
    hy = personal_impact(Profile(housing="rent", savings=10_000), 100, 0, "2023-02-01")
    assert by_topic(hy)["Savings"]["monthly"] < 0  # more interest earned = lower net cost
    bank = personal_impact(Profile(housing="rent", savings=10_000, savings_kind="bank"), 100, 0, "2023-02-01")
    assert by_topic(bank)["Savings"]["monthly"] == 0.0


def test_share_of_income_and_state():
    r = personal_impact(Profile(housing="rent", card_balance=12_000, income="$60k–$100k", state="TX"), 50, 0, "2023-03-22")
    assert r.share_of_income == round(r.monthly_total / (80_000 / 12) * 100, 2)
    assert "Texas" in by_topic(r)["Jobs where you live"]["text"]


def test_personal_data_never_reaches_llm_code():
    """No module that talks to an LLM imports the personal profile."""
    root = Path(__file__).resolve().parent.parent / "fed_decoder"
    llm_side = list((root / "llm").glob("*.py")) + list((root / "chat").glob("*.py")) + [
        root / "cards" / "builder.py", root / "cards" / "context.py", root / "cards" / "personal_note.py"]
    for f in llm_side:
        tree = ast.parse(f.read_text())
        names = [a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names] + \
                [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any("personal" in x for x in names), f"{f.name} imports personal data"


def test_ai_labels_carry_no_amounts_income_or_location():
    from fed_decoder.analysis.personal import ai_labels

    p = Profile(housing="arm", mortgage_balance=412_345, card_balance=7_777, savings=55_000, income="$100k–$150k", state="NY",
                car_loan="shopping", car_amount=31_000)
    labels = ai_labels(p)
    blob = " ".join(labels)
    assert not any(ch.isdigit() for ch in blob)
    assert "New York" not in blob and "NY" not in blob and "$" not in blob
    assert "has an adjustable-rate mortgage" in labels


def test_personal_note_prompt_contains_only_labels(monkeypatch, tmp_path):
    from fed_decoder.cards import personal_note as pn
    from fed_decoder.cards.context import build_context

    seen = {}

    def fake_generate(messages, **kw):
        seen["prompt"] = messages[-1]["content"]
        return None

    monkeypatch.setattr(pn, "generate", fake_generate)
    monkeypatch.setattr(pn, "CACHE", tmp_path / "notes.json")
    pn.personal_note(build_context("2024-09-18"), ["rents their home", "carries a credit card balance", "owes $9,999"])
    reader = seen["prompt"].split("THE READER:")[1]
    assert "rents their home" in reader and "9,999" not in reader  # anything with digits or symbols is dropped
