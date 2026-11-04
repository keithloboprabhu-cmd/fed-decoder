"""UI building blocks render and never invent numbers."""
import re

import pandas as pd

from fed_decoder.cards.context import build_context
from fed_decoder.cards.store import load_card
from fed_decoder.ui import components as ui


def test_components_render_for_a_real_meeting():
    ctx = build_context("2024-09-18")
    card = load_card("2024-09-18")
    assert ui.headline(card.decision.direction, card.decision.change_bps) == "The Fed cut interest rates by half a point"
    assert not ui.headline("hold", 0).endswith(".")  # interface headings have no trailing period
    html, notes = ui.redline_html(ctx["prev_statement"], ctx["statement"], card.changes)
    assert "<del>" in html and "<ins>" in html and len(notes) >= 1
    assert "−1.0" in ui.tone_scale_html(-1.0)
    assert 'class="term"' in ui.define("The FOMC met", ["FOMC"])
    assert ui.timeline_fig(pd.DataFrame({"meeting_date": pd.to_datetime(["2024-09-18"]), "direction": ["cut"], "change_bps": [-50],
                                         "target_low": [4.75], "target_high": [5.0]}), {"2024-09-18": -1.0}) is not None


def test_displayed_figures_come_from_context():
    """Every figure in the facts row is the code-computed decision."""
    ctx = build_context("2022-06-15")
    card = load_card("2022-06-15")
    html = ui.facts_html(card.decision)
    g = ctx["ground_truth"]
    assert f"+{g['change_bps']} basis points" in html and ui.fmt_range(g["target_low"], g["target_high"]) in html


def test_app_parses():
    import ast
    from pathlib import Path

    ast.parse((Path(__file__).resolve().parent.parent / "app.py").read_text())
