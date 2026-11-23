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


def track_caps(acts: pd.DataFrame, trk: str, year: int, total: int, track_of, quantile: float = 1.0,
               slack: int = 0) -> dict:
    """Longest stint teams have run on each compound at this track in earlier years (plus `slack`
    laps). A compound never run there is capped at its longest stint anywhere in earlier years."""
    a = acts[(acts["year"] < year) & acts["compound"].isin(COMPOUNDS)]
    here = a[[track_of(r, y) == trk for r, y in zip(a["race"], a["year"])]]
    caps = {}
    for comp in COMPOUNDS:
        h = here.loc[here["compound"] == comp, "laps"]
        g = a.loc[a["compound"] == comp, "laps"]
        base = h.quantile(quantile) if len(h) >= 3 else g.quantile(quantile)
        caps[comp] = int(min(total, base + slack))
    return caps


def evaluate(d: pd.DataFrame, c: pd.DataFrame, years, ridge: float, k: float,
             max_stint: dict | None = None, caps_by_track: dict | None = None,
             runs: pd.DataFrame | None = None, weekend: dict | None = None) -> pd.DataFrame:
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
        if runs is not None and weekend is not None:      # this weekend's practice / sprint long runs
            fc = forecast.weekend_adjust(fc, runs[runs["race_id"] == rid], **weekend)
        hind = model.fit_race(this, prior=glob, ridge=ridge)
        pp = pl[(pl["track"] == trk) & (pl["year"] < year)]["pit_loss"]
        pit_f = pp.median() if len(pp) else pl[pl["year"] < year]["pit_loss"].median()
        pit_h = pl.loc[pl["race_id"] == rid, "pit_loss"]
        pit_h = pit_h.iloc[0] if len(pit_h) else pit_f
        total = int(total)
        if caps_by_track is not None:
            ms = track_caps(acts, trk, year, total, forecast.track, **caps_by_track)
        else:
            ms = max_stint or {k_: total for k_ in COMPOUNDS}
        f_plan = best_plan(fc, total, pit_f, ms)
        h_plan = best_plan(hind, total, pit_h, {k_: total for k_ in COMPOUNDS})   # benchmark never capped
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


# ---------- planning for the race as it might go, not just the forecast ----------

CIDX = {c: i for i, c in enumerate(COMPOUNDS)}
SC_HELP = 0.5        # a stop under safety car / VSC costs about half the usual pit-lane time
SC_REACH = 3         # a team can bring a planned stop forward or back this many laps to catch one


def plan_matrix(total_laps: int, max_stint: dict, max_stops: int = 2):
    """All legal plans as arrays: compound index and stint length per stint (padded to 3)."""
    C, L = [], []
    for comps, lens in plans(total_laps, max_stint, max_stops=max_stops):
        C.append([CIDX[c] for c in comps] + [0] * (3 - len(comps)))
        L.append(list(lens) + [0] * (3 - len(lens)))
    C, L = np.array(C), np.array(L)
    stops = (L > 0).sum(1) - 1
    stop_laps = np.cumsum(L, axis=1)[:, :2] * (np.arange(2)[None, :] < stops[:, None])   # 0 = no stop
    return C, L, stops, stop_laps


def plan_times(p: dict, total_laps: int, C, L, stops, stop_laps, pit_loss: float, sc_near=None) -> np.ndarray:
    """Race time lost (tyres + pit lane) for every plan at once. sc_near[lap] = chance (or 0/1
    in hindsight) that a stop planned on that lap can be made under a safety car."""
    tab = cost_table(p, total_laps)
    T = np.stack([tab[c] for c in COMPOUNDS])                     # [3, total_laps + 1]
    tyres = T[C, L].sum(1)
    pit = pit_loss * stops.astype(float)
    if sc_near is not None:
        help_ = np.where(stop_laps > 0, sc_near[np.clip(stop_laps, 0, total_laps)], 0.0).sum(1)
        pit = pit - SC_HELP * pit_loss * help_
    return tyres + pit


def sc_rate(d: pd.DataFrame) -> pd.DataFrame:
    """Safety car / VSC periods started per lap, per race (from the leader's track status)."""
    lead = d[d["pos"] == 1].sort_values(["race_id", "lap"])
    on = lead["status"].str.contains("4|6|7", na=False).astype(bool)
    starts = on & ~on.groupby(lead["race_id"]).shift(1, fill_value=False)
    g = lead.assign(start=starts).groupby(["race_id", "year", "race"], as_index=False)
    return g.agg(periods=("start", "sum"), laps=("lap", "max"))


def wear_spread(past: pd.DataFrame) -> pd.DataFrame:
    """How far individual races have strayed from their track's usual wear: each past race's
    parameters minus the average of its track (tracks with 2+ races). Sampling these rows gives
    realistic 'this year is different' scenarios."""
    from . import model
    h = past[past.groupby("track")["track"].transform("size") >= 2]
    dev = pd.DataFrame(0.0, index=h.index, columns=model.PARAMS)
    for p in model.PARAMS:
        comp = p.split("_")[-1]
        used = h[f"laps_{comp}"] >= 100 if comp in COMPOUNDS else pd.Series(True, index=h.index)
        mean = h[p].where(used).groupby(h["track"]).transform("mean")
        dev[p] = (h[p] - mean).where(used, 0.0).fillna(0.0)
    return dev


def robust_choice(fc: dict, dev: pd.DataFrame, total: int, pit_f: float, sc_per_lap: float,
                  mats, n: int = 60, seed: int = 0, reach: int = SC_REACH) -> int:
    """Index of the plan with the lowest average race time across `n` simulated versions of
    the race (wear varied by sampled past deviations) and the expected safety-car help."""
    C, L, stops, stop_laps = mats
    p_sc = 1 - (1 - sc_per_lap) ** (2 * reach + 1)                 # chance an SC falls within reach
    sc_near = np.full(total + 1, p_sc)
    rng = np.random.default_rng(seed)
    rows = dev.to_numpy()[rng.integers(0, len(dev), n)] if len(dev) else np.zeros((1, len(dev.columns)))
    tot = np.zeros(len(C))
    for r in rows:
        p = {k: fc[k] + v for k, v in zip(dev.columns, r)}
        tot += plan_times(p, total, C, L, stops, stop_laps, pit_f, sc_near)
    return int(np.argmin(tot))


def describe(C, L, i) -> str:
    return " > ".join(f"{COMPOUNDS[c][0]}{l}" for c, l in zip(C[i], L[i]) if l > 0)


def evaluate_robust(d: pd.DataFrame, c: pd.DataFrame, years, ridge: float, k: float,
                    n: int = 60, reach: int = SC_REACH, use_spread: bool = True, use_sc: bool = True) -> pd.DataFrame:
    """Like evaluate(), but scores every plan against what actually happened, safety cars
    included: in hindsight a stop within `reach` laps of a real SC/VSC lap costs half.
    Compares three pre-race choices: the plain forecast plan, the plan that is best on average
    over simulated races (robust), and the winner's actual plan."""
    from . import forecast, model
    pl = pit_losses(d)
    pl["track"] = [forecast.track(a, b) for a, b in zip(pl["race"], pl["year"])]
    scr = sc_rate(d)
    scr["track"] = [forecast.track(a, b) for a, b in zip(scr["race"], scr["year"])]
    acts = actual_strategies(d)
    lead = d[d["pos"] == 1]
    rows, cache = [], {}
    races = d[d["year"].isin(years)][["race_id", "date", "race", "year", "total_laps"]].drop_duplicates("race_id").sort_values("date")
    for rid, date, race, year, total in races.itertuples(index=False):
        a = acts[acts["race_id"] == rid]
        if a.empty or not a["compound"].isin(COMPOUNDS).all():
            continue
        this = c[c["race_id"] == rid]
        if this["compound"].nunique() < 2:
            continue
        past_laps = c[c["date"] < date]
        key = past_laps["race_id"].nunique()
        if key not in cache:
            glob = forecast.typical(model.fit_all(past_laps, ridge=1.0))
            past = forecast.race_params(past_laps, glob, ridge)
            cache = {key: (past, glob, wear_spread(past))}
        past, glob, dev = cache[key]
        total = int(total)
        trk = forecast.track(race, year)
        fc = forecast.track_forecast(past, trk, glob, k)
        hind = model.fit_race(this, prior=glob, ridge=ridge)
        pp = pl[(pl["track"] == trk) & (pl["year"] < year)]["pit_loss"]
        pit_f = pp.median() if len(pp) else pl[pl["year"] < year]["pit_loss"].median()
        ph = pl.loc[pl["race_id"] == rid, "pit_loss"]
        pit_h = ph.iloc[0] if len(ph) else pit_f
        hist = scr[(scr["track"] == trk) & (scr["year"] < year)]
        hist = hist if len(hist) else scr[scr["year"] < year]
        sc_per_lap = hist["periods"].sum() / hist["laps"].sum()

        mats = plan_matrix(total, {k_: total for k_ in COMPOUNDS})
        C, L, stops, stop_laps = mats
        # what really happened: laps on which a stop could have been made under SC/VSC
        sc_laps = lead.loc[(lead["race_id"] == rid) & lead["status"].str.contains("4|6|7", na=False), "lap"].to_numpy()
        near = np.zeros(total + 1)
        for s in sc_laps:
            near[max(0, s - reach): min(total, s + reach) + 1] = 1.0
        truth = plan_times(hind, total, C, L, stops, stop_laps, pit_h, near)
        best = truth.min()

        plain = int(np.argmin(plan_times(fc, total, C, L, stops, stop_laps, pit_f)))
        spread = dev if use_spread else dev.iloc[:0]
        rob = robust_choice(fc, spread, total, pit_f, sc_per_lap if use_sc else 0.0, mats, n=n,
                            seed=int(date.value % 2**31), reach=reach)
        win = a[a["finish"] == a["finish"].min()].sort_values("stint")
        wl = list(win["laps"].clip(lower=1))
        wl[-1] += total - sum(wl)
        wc = list(win["compound"])
        tab = cost_table(hind, total)
        w_stops = np.cumsum(wl)[:-1]
        w_time = (sum(tab[x][min(y, total)] for x, y in zip(wc, wl))
                  + pit_h * len(w_stops) - SC_HELP * pit_h * near[np.clip(w_stops, 0, total)].sum())
        rows.append(dict(race_id=rid, year=year, race=race, sc=len(sc_laps) > 0,
                         plain=describe(C, L, plain), robust=describe(C, L, rob),
                         hindsight=describe(C, L, int(np.argmin(truth))), winner=" > ".join(f"{x[0]}{y}" for x, y in zip(wc, wl)),
                         plain_stops=int(stops[plain]), robust_stops=int(stops[rob]), winner_stops=len(wc) - 1,
                         hindsight_stops=int(stops[int(np.argmin(truth))]),
                         plain_cost=truth[plain] - best, robust_cost=truth[rob] - best,
                         winner_cost=w_time - best))
    return pd.DataFrame(rows)
