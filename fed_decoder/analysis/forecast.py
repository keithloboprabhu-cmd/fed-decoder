"""Light forecast of the next FOMC decision (hold / cut / hike). Computed, not generated.

Signals, each measured with data available at the meeting:
  1. Taylor-rule gap. Variant: Taylor (1993) with core PCE inflation and the
     CBO output gap:
         i* = r* + pi + 0.5 * (pi - pi_target) + 0.5 * gap
     r* = 2.0 (Taylor's original), pi_target = 2.0,
     pi  = core PCE, year over year (PCEPILFE),
     gap = 100 * (GDPC1 - GDPPOT) / GDPPOT, latest reported quarter.
     Feature = i* - midpoint of the current target range.
  2. SEP gap: SEP median fed funds for the relevant year-end (current year
     before October, next year after) minus the current midpoint. Available
     from the December 2015 SEP on ALFRED; zero plus an availability flag before.
  3. Tone: dictionary tone of the current statement, and its change vs the
     average of the previous three statements.
  4. Momentum: sign of the most recent rate move.

Model: multinomial logistic regression (scikit-learn defaults, C=1.0),
standardized features. A class-balanced variant was also tried; it catches
more moves but loses to the no-change baseline overall (see README).
Backtest: walk-forward. At each meeting, train only on meeting pairs whose
outcome was already known, then predict the next decision.
Educational, not financial advice.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from fed_decoder import config
from fed_decoder.analysis import tone as tone_mod
from fed_decoder.data import store

R_STAR = 2.0
PI_TARGET = 2.0
CLASSES = ["cut", "hold", "hike"]
FEATURES = ["taylor_gap", "sep_gap", "sep_avail", "tone", "tone_trend", "last_move"]
BACKTEST_PATH = config.DATA_DIR / "forecast_backtest.parquet"
MIN_TRAIN = 40


def taylor_rate(when: pd.Timestamp) -> dict | None:
    pce = store.yoy_asof("PCEPILFE", when)
    gdp = store.value_asof("GDPC1", when)
    if not pce or not gdp:
        return None
    pot = store.series("GDPPOT")
    pot_v = float(pot[pot.index <= gdp[0]].iloc[-1])
    gap = 100 * (gdp[1] - pot_v) / pot_v
    pi = pce[1]
    i_star = R_STAR + pi + 0.5 * (pi - PI_TARGET) + 0.5 * gap
    return {"rate": round(i_star, 2), "core_pce": pi, "output_gap": round(gap, 2)}


def sep_median_for(when: pd.Timestamp) -> float | None:
    p = config.DATA_DIR / "sep_vintages.parquet"
    if not p.exists():
        return None
    sep = pd.read_parquet(p)
    sep["asof"] = pd.to_datetime(sep["asof"])
    sep = sep[sep["asof"] <= pd.Timestamp(when) + pd.Timedelta(days=1)]
    if sep.empty:
        return None
    latest = sep[sep["asof"] == sep["asof"].max()]
    year = when.year if when.month < 10 else when.year + 1
    row = latest[latest["year"] == year]
    if row.empty:
        row = latest.sort_values("year").head(1)
    return float(row["median"].iloc[0])


def build_features() -> pd.DataFrame:
    stm = store.statements()
    gt = store.ground_truth().set_index("meeting_date")
    rows = []
    tones = [tone_mod.score(t).score for t in stm["statement_text"]]
    for i, d in enumerate(stm["meeting_date"]):
        g = gt.loc[d]
        mid = (g["target_low"] + g["target_high"]) / 2
        tr = taylor_rate(d)
        sep = sep_median_for(d)
        prev_moves = gt.loc[:d, "change_bps"]
        nz = prev_moves[prev_moves != 0]
        rows.append(
            {
                "meeting_date": d,
                "mid": mid,
                "taylor_rate": tr["rate"] if tr else np.nan,
                "taylor_gap": (tr["rate"] - mid) if tr else np.nan,
                "sep_median": sep if sep is not None else np.nan,
                "sep_gap": (sep - mid) if sep is not None else 0.0,
                "sep_avail": 1.0 if sep is not None else 0.0,
                "tone": tones[i],
                "tone_trend": tones[i] - (np.mean(tones[max(0, i - 3) : i]) if i > 0 else tones[i]),
                "last_move": float(np.sign(nz.iloc[-1])) if len(nz) else 0.0,
                "direction": g["direction"],
            }
        )
    f = pd.DataFrame(rows)
    f["next_direction"] = f["direction"].shift(-1)
    f["next_meeting"] = f["meeting_date"].shift(-1)
    return f


def _model():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))


def _proba(model, X: pd.DataFrame) -> np.ndarray:
    """Probabilities in CLASSES order, even if a class was absent in training."""
    p = model.predict_proba(X)
    out = np.zeros((len(X), len(CLASSES)))
    for j, c in enumerate(model.classes_):
        out[:, CLASSES.index(c)] = p[:, j]
    return out


def confidence_label(p_max: float) -> str:
    return "high" if p_max >= 0.75 else "medium" if p_max >= 0.55 else "low"


def backtest(features: pd.DataFrame | None = None) -> pd.DataFrame:
    f = (features if features is not None else build_features()).dropna(subset=["taylor_gap"]).reset_index(drop=True)
    labeled = f.dropna(subset=["next_direction"]).reset_index(drop=True)
    preds = []
    for t in range(MIN_TRAIN, len(f)):
        asof = f.loc[t, "meeting_date"]
        # pairs (s, s+1) whose outcome date is on or before this meeting
        train = labeled[labeled["next_meeting"] <= asof]
        if train["next_direction"].nunique() < 2:
            continue
        m = _model().fit(train[FEATURES], train["next_direction"])
        p = _proba(m, f.loc[[t], FEATURES])[0]
        preds.append(
            {
                "asof": asof,
                "target_meeting": f.loc[t, "next_meeting"],
                "actual": f.loc[t, "next_direction"],
                "p_cut": p[0], "p_hold": p[1], "p_hike": p[2],
                "pred": CLASSES[int(np.argmax(p))],
                "baseline": "hold",
            }
        )
    bt = pd.DataFrame(preds)
    bt.to_parquet(BACKTEST_PATH, index=False)
    return bt


def backtest_summary(bt: pd.DataFrame | None = None) -> dict:
    bt = bt if bt is not None else pd.read_parquet(BACKTEST_PATH)
    scored = bt.dropna(subset=["actual"])
    model_hit = float((scored["pred"] == scored["actual"]).mean())
    base_hit = float((scored["baseline"] == scored["actual"]).mean())
    moves = scored[scored["actual"] != "hold"]
    return {
        "n": int(len(scored)),
        "model_hit_rate": round(model_hit, 3),
        "baseline_hit_rate": round(base_hit, 3),
        "beats_baseline": model_hit > base_hit,
        "model_hit_rate_on_moves": round(float((moves["pred"] == moves["actual"]).mean()), 3) if len(moves) else None,
        "start": str(scored["asof"].min().date()),
        "end": str(scored["asof"].max().date()),
    }


@dataclass
class Forecast:
    asof: str
    p_cut: float
    p_hold: float
    p_hike: float
    most_likely: str
    confidence: str
    signals: dict
    backtest: dict
    note: str = "Educational, not financial advice."

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def forecast_next() -> Forecast:
    f = build_features()
    latest = f.iloc[-1].copy()
    today = pd.Timestamp.today().normalize()
    # Refresh the macro signals with today's data (the latest meeting's tone stays).
    tr = taylor_rate(today)
    sep = sep_median_for(today)
    if tr:
        latest["taylor_rate"], latest["taylor_gap"] = tr["rate"], tr["rate"] - latest["mid"]
    if sep is not None:
        latest["sep_median"], latest["sep_gap"], latest["sep_avail"] = sep, sep - latest["mid"], 1.0
    train = f.dropna(subset=["taylor_gap", "next_direction"])
    m = _model().fit(train[FEATURES], train["next_direction"])
    p = _proba(m, pd.DataFrame([latest[FEATURES]]))[0]
    summary = backtest_summary() if BACKTEST_PATH.exists() else {}
    return Forecast(
        asof=str(latest["meeting_date"].date()),
        p_cut=round(float(p[0]), 3),
        p_hold=round(float(p[1]), 3),
        p_hike=round(float(p[2]), 3),
        most_likely=CLASSES[int(np.argmax(p))],
        confidence=confidence_label(float(p.max())),
        signals={
            "taylor_rate": round(float(latest["taylor_rate"]), 2),
            "taylor_inputs": tr,
            "current_mid": float(latest["mid"]),
            "sep_median": None if pd.isna(latest["sep_median"]) else float(latest["sep_median"]),
            "tone": float(latest["tone"]),
            "tone_trend": round(float(latest["tone_trend"]), 2),
            "last_move": float(latest["last_move"]),
        },
        backtest=summary,
    )
