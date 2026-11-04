import pandas as pd

from fed_decoder.analysis import forecast as F
from fed_decoder.chat.tools import resolve_meeting


def test_backtest_has_no_lookahead(monkeypatch):
    """Every training row's outcome must be known on or before the prediction date."""
    feats = F.build_features()
    seen = []
    real_model = F._model

    class Spy:
        def __init__(self):
            self.m = real_model()

        def fit(self, X, y):
            seen.append(X.index)
            self.m.fit(X, y)
            return self

        def predict_proba(self, X):
            return self.m.predict_proba(X)

        @property
        def classes_(self):
            return self.m.classes_

    monkeypatch.setattr(F, "BACKTEST_PATH", F.config.CACHE_DIR / "bt_test.parquet")
    F.config.CACHE_DIR.mkdir(exist_ok=True)
    monkeypatch.setattr(F, "_model", Spy)
    bt = F.backtest(feats)
    labeled = feats.dropna(subset=["taylor_gap"]).dropna(subset=["next_direction"]).reset_index(drop=True)
    for idx, asof in zip(seen, bt["asof"]):
        assert (labeled.loc[idx, "next_meeting"] <= asof).all()


def test_forecast_probabilities_sum_to_one():
    f = F.forecast_next()
    assert abs(f.p_cut + f.p_hold + f.p_hike - 1) < 0.002  # rounded to 3 decimals
    assert f.note == "Educational, not financial advice."


def test_resolve_month_prefers_meeting_that_moved():
    assert resolve_meeting("March 2020") == pd.Timestamp("2020-03-15")
