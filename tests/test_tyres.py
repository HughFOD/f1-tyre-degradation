"""Checks: no forecast uses its own race or later ones, strategies obey the rules, and the
lap filters remove what they should."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tyres import data, forecast, model, strategy  # noqa: E402

WEAR = {"SOFT": (0.10, -0.6), "MEDIUM": (0.06, -0.3), "HARD": (0.03, 0.0)}   # s/lap, offset vs hard


def fake_laps(races=8, drivers=8, laps=40, seed=0) -> pd.DataFrame:
    """Made-up dry races: every driver one-stops (on different laps), half start on soft, half on
    medium, then hard."""
    rng = np.random.default_rng(seed)
    rows = []
    for r in range(races):
        date = pd.Timestamp("2023-03-01") + pd.to_timedelta(14 * r, unit="D")
        for i in range(drivers):
            # drivers stop on different laps: that is what lets fuel and wear be told apart
            stop = 12 + (3 * i + r) % 14
            first = "SOFT" if i % 2 == 0 else "MEDIUM"
            pace = 90 + 0.2 * i
            for lap in range(1, laps + 1):
                comp, age = (first, lap) if lap <= stop else ("HARD", lap - stop)
                w, off = WEAR[comp]
                t = pace - 0.06 * lap + off + w * age + rng.normal(0, 0.15)
                rows.append(dict(driver=f"D{i}", team="T", lap=lap, lap_time=t, compound=comp,
                                 stint=1 if lap <= stop else 2, tyre_age=age, fresh=True, pos=i + 1,
                                 status="1", pit_in=lap == stop, pit_out=lap == stop + 1, accurate=True,
                                 deleted=False, session_time=lap * 90 + i * 3.0, track_temp=35.0,
                                 year=2023 + (r >= races // 2), race=f"GP{r % 4}", date=date,
                                 total_laps=laps, round=r + 1, race_id=f"R{r:02d}"))
    return pd.DataFrame(rows)


def test_model_recovers_known_wear():
    c = data.clean_laps(fake_laps(), min_gap=None)
    p = model.fit_race(c[c["race_id"] == "R00"], ridge=0.01)
    assert p["fuel"] == pytest.approx(-0.06, abs=0.02)
    for k, (w, off) in WEAR.items():
        assert model.loss_after(p, k, 10) == pytest.approx(10 * w, abs=0.25)


def test_clean_laps_drops_pit_laps_lap_one_and_neutralised_laps():
    d = fake_laps(races=1)
    d.loc[d["lap"] == 7, "status"] = "14"          # safety car on lap 7
    c = data.clean_laps(d, min_gap=None)
    assert not c["pit_in"].any() and not c["pit_out"].any()
    assert (c["lap"] > 1).all() and not (c["lap"] == 7).any()


def test_gap_to_car_ahead():
    d = data.add_gap(fake_laps(races=1))
    assert np.isinf(d.loc[d["pos"] == 1, "gap_ahead"]).all()
    assert np.allclose(d.loc[d["pos"] == 2, "gap_ahead"], 3.0)


def test_forecasts_only_use_earlier_races(monkeypatch):
    seen = []
    orig = model.fit_all

    def spy(c, *a, **k):
        seen.append(c["date"].max())
        return orig(c, *a, **k)

    monkeypatch.setattr(model, "fit_all", spy)
    c = data.clean_laps(fake_laps(), min_gap=None)
    test_years = [2024]
    w = forecast.walk_forward(c, test_years, ridge=100, k=0.3)
    first_test = c.loc[c["year"].isin(test_years), "date"].min()
    assert seen and max(seen) < c["date"].max()
    assert min(seen) < first_test
    for rid in w["race_id"].unique():                    # every forecast row's race is after its history
        assert c.loc[c["race_id"] == rid, "date"].iloc[0] >= first_test


def test_plans_obey_the_rules():
    p = {"fuel": -0.06, **{f"offset_{k}": v[1] for k, v in WEAR.items()},
         **{f"wear_{k}": v[0] for k, v in WEAR.items()}, **{f"curve_{k}": 0.0 for k in WEAR}}
    ms = {k: 50 for k in WEAR}
    for comps, lens in strategy.plans(50, ms):
        assert len(set(comps)) >= 2 and sum(lens) == 50 and min(lens) >= 5
    best = strategy.best_plan(p, 50, pit_loss=22, max_stint=ms)
    assert best["stops"] in (1, 2)


def test_tyre_cost_never_falls_with_age():
    p = {"offset_SOFT": 0.0, "wear_SOFT": 0.05, "curve_SOFT": -0.5}    # a curve that bends down
    costs = [strategy.tyre_cost(p, "SOFT", L) for L in range(1, 60)]
    per_lap = np.diff([0] + costs)
    assert (np.diff(per_lap) >= -1e-9).all()


def test_long_runs_keep_only_race_like_running():
    o = fake_laps(races=1)
    o["session"] = "FP2"
    o.loc[o["lap"] == 10, "lap_time"] += 5          # a push lap / traffic: >3% off, dropped
    o.loc[o["lap"] == 20, "status"] = "2"            # yellow flag: dropped
    runs = data.long_runs(o)
    assert len(runs) and (runs["laps"] >= 5).all()
    assert set(runs["compound"]) <= set(data.DRY)


def test_weekend_shift_is_zero_without_practice():
    w = pd.DataFrame({"track_history": [0.05, 0.10], "wk_sum_all": [0.0, 0.0], "wk_n_all": [0, 0]})
    out = forecast.add_weekend(w, beta=0.15, k=10)
    assert np.allclose(out["weekend"], w["track_history"])


def test_ranges_use_only_earlier_seasons():
    rng = np.random.default_rng(1)
    n = 200
    w = pd.DataFrame({"year": np.repeat([2023, 2024], n), "compound": "HARD",
                      "weekend": 0.05, "slope": 0.05 + rng.normal(0, 0.02, 2 * n)})
    w.loc[w["year"] == 2024, "slope"] += 10           # a wild later season must not affect its own range
    out = forecast.add_ranges(w)
    assert out.loc[out["year"] == 2023, "range_low"].isna().all()      # nothing earlier to learn from
    width = (out["range_high"] - out["range_low"]).dropna()
    assert (width < 0.2).all()                                          # built from 2023's small misses only
