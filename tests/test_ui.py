"""UI building blocks render and never invent numbers."""
import re

from fed_decoder.cards.context import build_context
from fed_decoder.cards.store import load_card
from fed_decoder.analysis.votes import dissent_details
from fed_decoder.ui import components as ui


def test_components_render_for_a_real_meeting():
    ctx = build_context("2024-09-18")
    card = load_card("2024-09-18")
    d = card.decision
    assert ui.headline(d.direction, d.change_bps) == "The Fed cut interest rates by half a point"
    assert ui.arrow_chip("cut", -50) == ("▼ −0.50", "cut") and ui.arrow_chip("hold", 0) == ("→ held", "hold")
    details = dissent_details(ctx["statement"], d.direction, d.dissenters, d.change_bps)
    assert [x["lean"] for x in details] == ["hawk"]  # Bowman wanted a smaller cut
    head = ui.verdict_headline(d, details)
    assert head == "Cut to 4.75–5.00%. One wanted less." and len(head.split()) <= 8
    items = ui.changed_sentences(ctx["prev_statement"], ctx["statement"], card.changes)
    assert items and any("<del>" in ui.redline_html(i) or "<ins>" in ui.redline_html(i) for i in items)
    assert ui.vote_dots(11, details, []).count('<span class="dot') == 12
    assert 'class="term"' in ui.term("dissent") and "data-def" in ui.term("SEP")
    assert "left:" in ui.tone_stripe(-1.0, [0.0, 0.5])
    assert ui.sparkline([1, 2, 3]).startswith("<svg")


def test_displayed_figures_come_from_context():
    """Every figure in the verdict is the code-computed decision."""
    ctx = build_context("2022-06-15")
    card = load_card("2022-06-15")
    d = card.decision
    g = ctx["ground_truth"]
    head = ui.verdict_headline(d, dissent_details(ctx["statement"], d.direction, d.dissenters, d.change_bps))
    assert ui.fmt_range(g["target_low"], g["target_high"]) in head
    assert ui.arrow_chip(d.direction, d.change_bps)[0] == f"▲ +{g['change_bps'] / 100:.2f}"
    assert set(re.findall(r"\d+(?:\.\d+)?", head)) <= {f"{g['target_low']:.2f}", f"{g['target_high']:.2f}"}


def test_money_never_shows_zero():
    assert ui.signed_money(0.0) == "no change" and ui.signed_money(-12.4) == "−$12/mo"


def test_plain_never_adds_numbers():
    s = "The Committee decided to maintain the target range at 5¼ to 5½ percent in support of its goals."
    out = ui.plain(s, 10)
    assert len(out.split()) <= 10 and set(re.findall(r"\d", out)) <= set(re.findall(r"\d", s))


def test_app_parses():
    import ast
    from pathlib import Path

    ast.parse((Path(__file__).resolve().parent.parent / "app.py").read_text())
