"""Ideas tried to improve the forecasts and plans, kept so every number in the README can be
reproduced. Each was judged on the validation season (2023) first; only an idea that helped there
would have been run on 2024-2026. The noise-floor analysis uses 2024-2026 because it is
descriptive (it fits nothing).
"""
import itertools

import numpy as np
import pandas as pd

from . import forecast, model, strategy

VALIDATION = [2023]


def temperature(params: pd.DataFrame, last_year: int = 2023) -> pd.DataFrame:
    """At the same track, do hotter races wear tyres more? Race-to-race change in time lost after
    20 laps vs change in track temperature, both relative to the track's average (2019-2023)."""
    r = params[params["year"] <= last_year].copy()
    rows = []
    for k in model.COMPOUNDS:
        u = r[r[f"laps_{k}"] >= 100].copy()
        u["loss20"] = model.loss_after(u, k, 20)
        u = u[u.groupby("track")["track"].transform("size") >= 2]
        dl = u["loss20"] - u.groupby("track")["loss20"].transform("mean")
        dt = u["track_temp"] - u.groupby("track")["track_temp"].transform("mean")
        rows.append({"compound": k, "races": len(u), "s per 20 laps per degC": float(np.polyfit(dt, dl, 1)[0]),
                     "correlation": float(np.corrcoef(dt, dl)[0, 1])})
    return pd.DataFrame(rows)


def _team_adjusted(w: pd.DataFrame, by: str, k: float, window: int) -> np.ndarray:
    """Forecast + the team's (or driver's) average miss in its last `window` races, shrunk by k."""
    out = np.full(len(w), np.nan)
    for n, idx in w.groupby("n").groups.items():
        past = w[(w["n"] < n) & (w["n"] >= n - window)]
        st = past.groupby(by)["res"].agg(["sum", "count"])
        g = w.loc[idx]
        out[w.index.get_indexer(idx)] = (g["track_history"] + g[by].map(st["sum"]).fillna(0.0)
                                         / (g[by].map(st["count"]).fillna(0.0) + k))
    return out


def team_wear(c: pd.DataFrame, ridge: float, k: float) -> dict:
    """Do some teams (or drivers) consistently wear tyres more than forecast? Settings picked on
    2023; the best is then scored on 2024-2026."""
    w = forecast.walk_forward(c, list(range(2021, 2027)), ridge, k).reset_index(drop=True)
    w["res"] = w["slope"] - w["track_history"]
    order = w[["race_id", "date"]].drop_duplicates().sort_values("date").reset_index(drop=True)
    w = w.merge(order.assign(n=range(len(order)))[["race_id", "n"]], on="race_id")

    def mae(col, years):
        m = w["year"].isin(years)
        return float(((w.loc[m, col] - w.loc[m, "slope"]).abs() * 19).mean())

    grid = []
    for by, kk, win in itertools.product(["team", "driver"], [10, 30, 100], [5, 10, 20]):
        w["adj"] = _team_adjusted(w, by, kk, win)
        grid.append((mae("adj", VALIDATION), by, kk, win))
    best = min(grid)
    w["adj"] = _team_adjusted(w, best[1], best[2], best[3])
    hold = [2024, 2025, 2026]
    return {"best setting (2023)": f"{best[1]}, k={best[2]}, last {best[3]} races",
            "2023 without": mae("track_history", VALIDATION), "2023 with": best[0],
            "2024-26 without": mae("track_history", hold), "2024-26 with": mae("adj", hold)}


def robust_planning(d: pd.DataFrame, c: pd.DataFrame, ridge: float, k: float) -> pd.DataFrame:
    """Plan for the race as it might go: average over simulated races (wear varied as much as it
    has year to year at each track; safety cars as often as they've happened there)."""
    rows = []
    for name, kw in (("wear spread + safety cars", {}), ("safety cars only", {"use_spread": False}),
                     ("wear spread only", {"use_sc": False})):
        e = strategy.evaluate_robust(d, c, VALIDATION, ridge, k, **kw)
        rows.append({"variant": name, "races": len(e),
                     "plain plan, median s lost": float(e["plain_cost"].median()),
                     "robust plan, median s lost": float(e["robust_cost"].median()),
                     "plain starts on soft": float(e["plain"].str.startswith("S").mean()),
                     "robust starts on soft": float(e["robust"].str.startswith("S").mean())})
    return pd.DataFrame(rows)


def stint_caps(d: pd.DataFrame, c: pd.DataFrame, ridge: float, k: float) -> pd.DataFrame:
    """Only plan stints as long as teams have actually run each compound at that track."""
    rows = []
    for name, caps in (("no caps", None), ("longest stint run there", {"quantile": 1.0}),
                       ("90th percentile", {"quantile": 0.9}), ("75th percentile", {"quantile": 0.75})):
        e = strategy.evaluate(d, c, VALIDATION, ridge, k, caps_by_track=caps)
        rows.append({"stint limit": name, "races": len(e),
                     "mean s lost vs best plan (lap-time model)": float(e["plan_cost"].mean()),
                     "stops match winner": float((e["plan_stops"] == e["winner_stops"]).mean()),
                     "first stop vs winner, laps later": float((e["plan_first_stop"] - e["winner_first_stop"]).mean()),
                     "starts on soft": float(e["plan"].str.startswith("S").mean())})
    return pd.DataFrame(rows)


def noise_floor(w: pd.DataFrame, max_age_gap: int = 3) -> dict:
    """How differently do stints behave that should behave the same: same race, same compound,
    tyre ages within a few laps at both ends? With independent noise in each, the typical gap
    between two such stints is sqrt(2) times the per-stint noise."""
    diffs, mates = [], []
    for _, g in w.groupby(["race_id", "compound"]):
        g = g.reset_index(drop=True)
        for i, j in itertools.combinations(range(len(g)), 2):
            a, b = g.iloc[i], g.iloc[j]
            if abs(a["age0"] - b["age0"]) <= max_age_gap and abs(a["age1"] - b["age1"]) <= max_age_gap:
                diffs.append(abs(a["slope"] - b["slope"]) * 19)
                mates.append(a["team"] == b["team"])
    diffs, mates = np.array(diffs), np.array(mates)
    return {"matched pairs": int(len(diffs)), "teammate pairs": int(mates.sum()),
            "unpredictable part, s per 20 laps (all pairs)": float(diffs.mean() / np.sqrt(2)),
            "unpredictable part, s per 20 laps (teammates)": float(diffs[mates].mean() / np.sqrt(2))}
