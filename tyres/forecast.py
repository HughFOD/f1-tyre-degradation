"""Forecasting tyre wear for a race from earlier races only, and testing it stint by stint."""
import numpy as np
import pandas as pd

from . import model

SAME_TRACK = {"Mexican Grand Prix": "Mexico City Grand Prix", "Brazilian Grand Prix": "São Paulo Grand Prix",
              "Styrian Grand Prix": "Austrian Grand Prix", "70th Anniversary Grand Prix": "British Grand Prix"}


def track(race: str, year: int) -> str:
    """One name per circuit. In 2026 the Spanish GP moved to Madrid and Barcelona's race was renamed."""
    if year >= 2026 and race == "Spanish Grand Prix":
        return "Madrid"
    if race == "Barcelona Grand Prix":
        return "Spanish Grand Prix"
    return SAME_TRACK.get(race, race)


def race_params(c: pd.DataFrame, prior: dict, ridge: float) -> pd.DataFrame:
    r = model.fit_all(c, prior=prior, ridge=ridge)
    r["track"] = [track(a, b) for a, b in zip(r["race"], r["year"])]
    return r


def typical(r: pd.DataFrame) -> dict:
    """Median of each parameter over races where the compound was really used."""
    out = {"fuel": r["fuel"].median()}
    for k in model.COMPOUNDS:
        u = r[r[f"laps_{k}"] >= 100]
        for p in ("offset", "wear", "curve"):
            out[f"{p}_{k}"] = u[f"{p}_{k}"].median() if len(u) else 0.0
    return out


def track_forecast(past: pd.DataFrame, trk: str, glob: dict, k: float, halflife: float = 2.0) -> dict:
    """This track's earlier races (recent years weighted more), blended with the typical race:
    weight n/(n+k) on the track's own history, where n is the effective number of past races."""
    h = past[past["track"] == trk]
    if h.empty:
        return dict(glob)
    w = 0.5 ** ((h["year"].max() - h["year"]) / halflife)
    n = w.sum()
    a = n / (n + k)
    out = {}
    for p in model.PARAMS:
        comp = p.split("_")[-1]
        if comp in model.COMPOUNDS:
            used = h[f"laps_{comp}"] >= 100
            ww = w[used]
            if ww.sum() == 0:
                out[p] = glob[p]
                continue
            nn = ww.sum()
            out[p] = (nn / (nn + k)) * np.average(h.loc[used, p], weights=ww) + (k / (nn + k)) * glob[p]
        else:
            out[p] = a * np.average(h[p], weights=w) + (1 - a) * glob[p]
    return out


def stints(c: pd.DataFrame, min_laps: int = 8) -> pd.DataFrame:
    """One row per stint with enough clean laps: compound, tyre age at its first and last clean
    lap, and the actual lap-time trend (least-squares slope, seconds per lap)."""
    rows = []
    for (rid, drv, st), g in c.groupby(["race_id", "driver", "stint"], sort=False):
        if len(g) < min_laps or g["compound"].nunique() != 1:
            continue
        x, y = g["lap"].to_numpy(float), g["lap_time"].to_numpy(float)
        slope = np.polyfit(x, y, 1)[0]
        rows.append(dict(race_id=rid, year=g["year"].iloc[0], race=g["race"].iloc[0], date=g["date"].iloc[0],
                         driver=drv, team=g["team"].iloc[0], stint=st,
                         compound=g["compound"].iloc[0], age0=g["tyre_age"].min(), age1=g["tyre_age"].max(),
                         laps=len(g), slope=slope))
    s = pd.DataFrame(rows)
    s["track"] = [track(a, b) for a, b in zip(s["race"], s["year"])]
    return s


def predicted_slope(p: dict, compound: str, age0, age1) -> np.ndarray:
    """Average seconds per lap the car is expected to slow (or speed up) over the stint:
    fuel burn plus tyre wear between the first and last tyre age."""
    age0, age1 = np.asarray(age0, float), np.asarray(age1, float)
    span = np.maximum(age1 - age0, 1)
    wear = (model.loss_after(p, compound, age1) - model.loss_after(p, compound, age0)) / span
    return p["fuel"] + wear


def weekend_signal(runs: pd.DataFrame, fc: dict) -> dict:
    """How this weekend's practice/sprint long runs compared with the track-history forecast:
    per compound and overall, the summed miss (actual minus forecast trend, s/lap) and the count."""
    if runs is None or runs.empty:
        return {}
    miss = runs["slope"].to_numpy() - np.concatenate(
        [predicted_slope(fc, comp, g["age0"], g["age1"]) for comp, g in runs.groupby("compound", sort=False)])
    comps = np.concatenate([g["compound"].to_numpy() for _, g in runs.groupby("compound", sort=False)])
    out = {"all": (float(miss.sum()), len(miss))}
    for comp in model.COMPOUNDS:
        m = comps == comp
        out[comp] = (float(miss[m].sum()), int(m.sum()))
    return out


def walk_forward(c: pd.DataFrame, years, ridge: float, k: float, first_train: int = 2018,
                 runs: pd.DataFrame | None = None) -> pd.DataFrame:
    """For every race in `years`: fit the parameters of all EARLIER races, forecast this race's
    wear from them, and compare with what its stints actually did. Also records two simpler
    forecasts (fuel only; typical race) and the hindsight fit of the race itself (not a forecast:
    a ceiling for how well wear can be described at all)."""
    st_all = stints(c)
    out = []
    races = c[c["year"].isin(years)][["race_id", "date"]].drop_duplicates().sort_values("date")
    fitted = {}
    for rid, date in races.itertuples(index=False):
        past_laps = c[(c["date"] < date) & (c["year"] >= first_train)]
        key = past_laps["race_id"].nunique()
        if key not in fitted:            # refit history only when it has grown
            r0 = model.fit_all(past_laps, ridge=1.0)
            glob = typical(r0)
            fitted = {key: (race_params(past_laps, glob, ridge), glob)}
        past, glob = fitted[key]
        s = st_all[st_all["race_id"] == rid]
        if s.empty:
            continue
        this = c[c["race_id"] == rid]
        trk = s["track"].iloc[0]
        fc = track_forecast(past, trk, glob, k)
        hind = model.fit_race(this, prior=glob, ridge=ridge) if this["compound"].nunique() >= 2 else None
        for comp, g in s.groupby("compound"):
            row = g[["race_id", "year", "race", "date", "track", "driver", "team", "stint", "compound", "age0", "age1",
                     "laps", "slope"]].copy()
            row["fuel_only"] = glob["fuel"]
            row["typical"] = predicted_slope(glob, comp, g["age0"], g["age1"])
            row["track_history"] = predicted_slope(fc, comp, g["age0"], g["age1"])
            row["hindsight"] = predicted_slope(hind, comp, g["age0"], g["age1"]) if hind else np.nan
            row["track_seen_before"] = (past["track"] == trk).any()
            if runs is not None:
                sig = weekend_signal(runs[runs["race_id"] == rid], fc)
                row["wk_sum_comp"], row["wk_n_comp"] = sig.get(comp, (0.0, 0))
                row["wk_sum_all"], row["wk_n_all"] = sig.get("all", (0.0, 0))
            out.append(row)
    return pd.concat(out, ignore_index=True)


FORECASTS = ["fuel_only", "typical", "track_history", "weekend", "hindsight"]


def add_weekend(w: pd.DataFrame, beta: float, k: float) -> pd.DataFrame:
    """Weekend forecast: track history shifted by this weekend's practice/sprint long runs
    (beta x their average miss vs the forecast, shrunk toward zero by k runs)."""
    w = w.copy()
    w["weekend"] = w["track_history"] + beta * w["wk_sum_all"] / (w["wk_n_all"] + k)
    return w


def score(w: pd.DataFrame, stint_laps: int = 20) -> pd.DataFrame:
    """Error in the time a stint loses, scaled to a 20-lap stint so it reads in seconds."""
    rows = []
    for f in [x for x in FORECASTS if x in w]:
        e = (w[f] - w["slope"]) * (stint_laps - 1)
        rows.append({"forecast": f, "stints": int(e.notna().sum()), "MAE (s per 20 laps)": e.abs().mean(),
                     "bias (s per 20 laps)": e.mean()})
    return pd.DataFrame(rows)


def walk_forward_live(c: pd.DataFrame, years, ridge: float, k: float, share: float = 0.4,
                      live_ridge: float | None = None) -> pd.DataFrame:
    """Mid-race update: at the point `share` of the way through each race, refit wear using that
    race's own clean laps so far, starting from the track-history forecast (so a compound nobody
    has used yet keeps its forecast). Scored on stints that start after that point."""
    live_ridge = ridge if live_ridge is None else live_ridge
    st_all = stints(c)
    out = []
    races = c[c["year"].isin(years)][["race_id", "date"]].drop_duplicates().sort_values("date")
    cache = {}
    for rid, date in races.itertuples(index=False):
        past_laps = c[c["date"] < date]
        key = past_laps["race_id"].nunique()
        if key not in cache:
            glob = typical(model.fit_all(past_laps, ridge=1.0))
            cache = {key: (race_params(past_laps, glob, ridge), glob)}
        past, glob = cache[key]
        this = c[c["race_id"] == rid]
        cut = int(share * this["total_laps"].iloc[0])
        later = st_all[st_all["race_id"] == rid]
        first_lap = this.groupby(["driver", "stint"])["lap"].min()
        later = later[[first_lap.get((d_, s_), 0) > cut for d_, s_ in zip(later["driver"], later["stint"])]]
        early = this[this["lap"] <= cut]
        if later.empty or early["driver"].nunique() < 5:
            continue
        fc = track_forecast(past, later["track"].iloc[0], glob, k)
        live = model.fit_race(early, prior=fc, ridge=live_ridge)
        for comp, g in later.groupby("compound"):
            row = g[["race_id", "year", "race", "track", "driver", "stint", "compound", "age0", "age1", "laps", "slope"]].copy()
            row["typical"] = predicted_slope(glob, comp, g["age0"], g["age1"])
            row["track_history"] = predicted_slope(fc, comp, g["age0"], g["age1"])
            row["live"] = predicted_slope(live, comp, g["age0"], g["age1"])
            row["used_before_cut"] = (early["compound"] == comp).any()
            out.append(row)
    return pd.concat(out, ignore_index=True)


def weekend_adjust(fc: dict, runs: pd.DataFrame | None, beta: float, k: float, per_compound: bool = False,
                   k_comp: float | None = None) -> dict:
    """Shift the track-history forecast by how this weekend's practice/sprint long runs compared
    with it: every compound's wear moves by beta x the shrunk average miss (s/lap). With
    per_compound, a compound that was run in practice uses its own miss (shrunk by k_comp)."""
    sig = weekend_signal(runs, fc) if runs is not None else {}
    if not sig:
        return dict(fc)
    s_all, n_all = sig["all"]
    out = dict(fc)
    for comp in model.COMPOUNDS:
        d = s_all / (n_all + k)
        if per_compound:
            s_c, n_c = sig[comp]
            if n_c:
                d = s_c / (n_c + (k_comp or k))
        out[f"wear_{comp}"] = fc[f"wear_{comp}"] + beta * d
    return out
