"""Pit strategy: enumerate one- and two-stop plans and find the fastest, given a wear forecast.

Race time of a plan = time lost to tyres (compound offset + wear, lap by lap) + time lost in the
pit lane. Fuel burn and the driver's base pace are the same whatever the plan, so they cancel.
The rules require at least two different dry compounds in a dry race.
"""
import itertools

import numpy as np
import pandas as pd

from . import model

COMPOUNDS = model.COMPOUNDS


def tyre_cost(p: dict, compound: str, laps: int, start_age: int = 1) -> float:
    """Seconds lost over a stint of `laps` laps relative to a hypothetical tyre that never wears
    and has the hard tyre's base speed. Wear is forced to be non-decreasing with age (a fitted
    curve can bend down at ages it has rarely seen; real tyres don't recover)."""
    age = np.arange(start_age, start_age + laps, dtype=float)
    loss = np.maximum.accumulate(np.maximum(model.loss_after(p, compound, age), 0.0))
    return float(laps * p[f"offset_{compound}"] + loss.sum())


def plans(total_laps: int, max_stint: dict, min_stint: int = 5, max_stops: int = 2):
    """Every (compounds, stint lengths) plan with 1..max_stops stops using >= 2 compounds,
    each stint within [min_stint, max_stint[compound]]."""
    for stops in range(1, max_stops + 1):
        for comps in itertools.product(COMPOUNDS, repeat=stops + 1):
            if len(set(comps)) < 2:
                continue
            if stops == 1:
                for a in range(min_stint, total_laps - min_stint + 1):
                    lens = (a, total_laps - a)
                    if all(l <= max_stint[c] for l, c in zip(lens, comps)):
                        yield comps, lens
            else:
                for a in range(min_stint, total_laps - 2 * min_stint + 1):
                    for b in range(min_stint, total_laps - a - min_stint + 1):
                        lens = (a, b, total_laps - a - b)
                        if all(l <= max_stint[c] for l, c in zip(lens, comps)):
                            yield comps, lens


def cost_table(p: dict, total_laps: int) -> dict:
    """cost[c][L] = tyre_cost(p, c, L), for every stint length up to the race distance."""
    return {c: np.array([0.0] + [tyre_cost(p, c, L) for L in range(1, total_laps + 1)]) for c in COMPOUNDS}


def plan_time(p: dict, comps, lens, pit_loss: float, table: dict | None = None) -> float:
    if table is not None:
        return sum(table[c][l] for c, l in zip(comps, lens)) + pit_loss * (len(comps) - 1)
    return sum(tyre_cost(p, c, l) for c, l in zip(comps, lens)) + pit_loss * (len(comps) - 1)


def best_plan(p: dict, total_laps: int, pit_loss: float, max_stint: dict) -> dict:
    best = None
    table = cost_table(p, total_laps)
    for comps, lens in plans(total_laps, max_stint):
        t = plan_time(p, comps, lens, pit_loss, table)
        if best is None or t < best["time"]:
            best = {"compounds": comps, "laps": lens, "time": t}
    best["stops"] = len(best["compounds"]) - 1
    best["first_stop"] = best["laps"][0]
    return best


# ---------- what the data says about each track ----------

def pit_losses(d: pd.DataFrame) -> pd.DataFrame:
    """Time lost to each green-flag pit stop: in-lap + out-lap minus two of the driver's typical
    laps that race. Stops under safety car / VSC are left out (they cost much less)."""
    d = d.sort_values(["race_id", "driver", "lap"])
    typical = d[(d["status"] == "1") & ~d["pit_in"] & ~d["pit_out"]].groupby(["race_id", "driver"])["lap_time"].median()
    nxt = d.groupby(["race_id", "driver"])[["lap_time", "status", "pit_out"]].shift(-1)
    stop = d["pit_in"] & nxt["pit_out"].astype("boolean").fillna(False).astype(bool) & (d["status"] == "1") & (nxt["status"] == "1")
    s = d[stop].assign(out_lap=nxt.loc[stop, "lap_time"])
    s["typical"] = [typical.get((r, dv), np.nan) for r, dv in zip(s["race_id"], s["driver"])]
    s["pit_loss"] = s["lap_time"] + s["out_lap"] - 2 * s["typical"]
    s = s[(s["pit_loss"] > 10) & (s["pit_loss"] < 40)]           # drop slow stops / repairs
    return s.groupby(["race_id", "year", "race"], as_index=False)["pit_loss"].median()


def actual_strategies(d: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    """Stints actually run by the top finishers: compound sequence and stint lengths."""
    last = d.sort_values("lap").groupby(["race_id", "driver"]).tail(1)
    fin = last[last["lap"] >= last.groupby("race_id")["lap"].transform("max")]   # ran full distance
    fin = fin[fin["pos"] <= top]
    keep = d.merge(fin[["race_id", "driver", "pos"]].rename(columns={"pos": "finish"}), on=["race_id", "driver"])
    st = (keep.groupby(["race_id", "year", "race", "driver", "finish", "stint"], as_index=False)
              .agg(compound=("compound", "first"), laps=("lap", "size"), sc_laps=("status", lambda s: s.str.contains("4|6|7").sum())))
    return st


def safety_car_laps(d: pd.DataFrame) -> pd.DataFrame:
    """Share of laps run under safety car or virtual safety car, per race."""
    lead = d[d["pos"] == 1]
    sc = lead["status"].str.contains("4|6|7")
    return lead.assign(sc=sc).groupby(["race_id", "year", "race"], as_index=False)["sc"].mean()


def evaluate(d: pd.DataFrame, c: pd.DataFrame, years, ridge: float, k: float,
             max_stint: dict | None = None) -> pd.DataFrame:
    """For every dry race in `years`, using only earlier races: forecast wear, take the fastest
    plan under that forecast, and score it with the wear the race actually showed (the hindsight
    fit). Scores the top-10 finishers' actual plans the same way. Costs are seconds slower than
    the best plan possible in hindsight."""
    from . import forecast
    pl = pit_losses(d)
    pl["track"] = [forecast.track(a, b) for a, b in zip(pl["race"], pl["year"])]
    acts = actual_strategies(d)
    rows = []
    races = d[d["year"].isin(years)][["race_id", "date", "race", "year", "total_laps"]].drop_duplicates("race_id").sort_values("date")
    cache = {}
    for rid, date, race, year, total in races.itertuples(index=False):
        a = acts[acts["race_id"] == rid]
        if a.empty or not a["compound"].isin(COMPOUNDS).all():
            continue                                  # wet or mixed race
        this = c[c["race_id"] == rid]
        if this["compound"].nunique() < 2:
            continue
        past_laps = c[c["date"] < date]
        key = past_laps["race_id"].nunique()
        if key not in cache:
            glob = forecast.typical(model.fit_all(past_laps, ridge=1.0))
            cache = {key: (forecast.race_params(past_laps, glob, ridge), glob)}
        past, glob = cache[key]
        trk = forecast.track(race, year)
        fc = forecast.track_forecast(past, trk, glob, k)
        hind = model.fit_race(this, prior=glob, ridge=ridge)
        pp = pl[(pl["track"] == trk) & (pl["year"] < year)]["pit_loss"]
        pit_f = pp.median() if len(pp) else pl[pl["year"] < year]["pit_loss"].median()
        pit_h = pl.loc[pl["race_id"] == rid, "pit_loss"]
        pit_h = pit_h.iloc[0] if len(pit_h) else pit_f
        ms = max_stint or {k_: int(total) for k_ in COMPOUNDS}
        total = int(total)
        f_plan = best_plan(fc, total, pit_f, ms)
        h_plan = best_plan(hind, total, pit_h, ms)
        tab = cost_table(hind, total)
        h_time = h_plan["time"]
        f_cost = plan_time(hind, f_plan["compounds"], f_plan["laps"], pit_h, tab) - h_time
        team_costs, team_stops = [], []
        for drv, g in a.groupby("driver"):
            g = g.sort_values("stint")
            lens = list(g["laps"].clip(lower=1))
            if sum(lens) != total:
                lens[-1] += total - sum(lens)
            team_costs.append(plan_time(hind, list(g["compound"]), lens, pit_h, tab) - h_time)
            team_stops.append(len(g) - 1)
        win = a[a["finish"] == a["finish"].min()].sort_values("stint")
        sc_share = (d[(d["race_id"] == rid) & (d["pos"] == 1)]["status"].str.contains("4|6|7")).mean()
        rows.append(dict(race_id=rid, year=year, race=race, laps=total, pit_loss=round(pit_h, 1), sc_share=sc_share,
                         plan=" > ".join(f"{c_[0]}{l_}" for c_, l_ in zip(f_plan["compounds"], f_plan["laps"])),
                         hindsight_plan=" > ".join(f"{c_[0]}{l_}" for c_, l_ in zip(h_plan["compounds"], h_plan["laps"])),
                         winner_plan=" > ".join(f"{c_[0]}{l_}" for c_, l_ in zip(win["compound"], win["laps"])),
                         plan_stops=f_plan["stops"], hindsight_stops=h_plan["stops"], winner_stops=len(win) - 1,
                         top10_typical_stops=int(pd.Series(team_stops).mode().iloc[0]),
                         plan_first_stop=f_plan["first_stop"], hindsight_first_stop=h_plan["first_stop"],
                         winner_first_stop=int(win["laps"].iloc[0]),
                         plan_cost=f_cost, top10_median_cost=float(np.median(team_costs)),
                         top10_best_cost=float(np.min(team_costs))))
    return pd.DataFrame(rows)
