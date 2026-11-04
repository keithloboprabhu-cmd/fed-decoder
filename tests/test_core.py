import json

import pytest

from fed_decoder.analysis import impact
from fed_decoder.analysis.diff import redline, sentence_changes, sentences
from fed_decoder.cards.rules import extract_decision, frac_to_float
from fed_decoder.data import store
from fed_decoder.data.ground_truth import parse_votes
from fed_decoder.llm import guardrail


def test_amortization_known_value():
    # $300,000 at 6% for 30 years = $1,798.65/month (standard table value)
    assert round(impact.monthly_payment(300_000, 6.0, 360), 2) == 1798.65
    r = impact.payment_impact("mortgage_30y", 300_000, 25, 6.0)
    assert r.monthly_after > r.monthly_before
    assert impact.payment_impact("credit_card", 5000, 100, 20.0).monthly_change == round(5000 * 0.01 / 12, 2)


def test_fractions():
    assert frac_to_float("5-3/4") == 5.75
    assert frac_to_float("1 3/4") == 1.75
    assert frac_to_float("1/4") == 0.25


def test_guardrail_numbers_and_quotes():
    ctx = "lower by 25 basis points to 3-3/4 percent; monthly_change: -15.2; 2024-09-18"
    assert guardrail.ungrounded_numbers("A 0.25 point cut to 3.75%; payments fall $15.20 in 2024.", ctx) == []
    assert guardrail.ungrounded_numbers("Rates fell to 7 percent.", ctx) == ["7"]
    assert guardrail.quote_in("“Inflation remains elevated.”", "Growth slowed. Inflation remains elevated. Jobs rose.")
    assert not guardrail.quote_in("Inflation is very high", "Inflation remains elevated.")


def test_sentence_split_keeps_names():
    s = sentences("Voting against was Michelle W. Bowman, who preferred less. The U.S. economy grew.")
    assert len(s) == 2


def test_redline_ops():
    ops = redline("growth was solid", "growth was strong")
    assert [o.op for o in ops if o.op != "equal"] == ["delete", "insert"]
    ch = sentence_changes("A b c. Inflation is high.", "A b c. Inflation is low.")
    assert ch[0].kind == "modified"


def test_vote_parser_variants():
    t = ("Voting for the monetary policy action were Jerome H. Powell, Chair, John C. Williams, Vice Chair; Lael Brainard; and Randal K. Quarles. "
         "Voting against the action were James Bullard, who preferred to lower; and Esther L. George and Eric S. Rosengren, who preferred to hold.")
    v = parse_votes(t)
    assert v["votes_for"] == 4 and v["votes_against"] == 3
    assert v["dissenters"] == ["James Bullard", "Esther L. George", "Eric S. Rosengren"]
    assert parse_votes("approved the following statement for release by a 12 – 0 vote:")["votes_for"] == 12


@pytest.mark.parametrize("date,direction,bps,hi", [
    ("2024-09-18", "cut", -50, 5.0),
    ("2008-12-16", "cut", -75, 0.25),
    ("2022-06-15", "hike", 75, 1.75),
    ("2020-03-15", "cut", -100, 0.25),
    ("2019-07-31", "cut", -25, 2.25),
])
def test_ground_truth_known_meetings(date, direction, bps, hi):
    gt = store.ground_truth().set_index("meeting_date").loc[date]
    assert (gt["direction"], int(gt["change_bps"]), float(gt["target_high"])) == (direction, bps, hi)


def test_rules_extractor_on_pasted_text():
    d = extract_decision("The Committee decided to lower the target range for the federal funds rate by 1/4 percentage point to 4 to 4-1/4 percent.")
    assert (d["direction"], d["change_bps"], d["target_low"], d["target_high"]) == ("cut", -25, 4.0, 4.25)


def test_every_meeting_has_a_valid_card():
    from fed_decoder.cards.store import all_cards

    cards = all_cards()
    assert len(cards) == len(store.statements())
    for c in cards.values():
        assert c.validated and -2 <= c.tone_score <= 2
        json.dumps(c.model_dump())
