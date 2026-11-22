"""Tyre degradation model.

For one race, every clean lap is explained as

    lap time = driver's pace that race                 (one number per driver: car + driver)
             + fuel effect x lap number                 (the car gets lighter, so faster, every lap)
             + compound offset                          (soft quicker than hard on new tyres)
             + compound wear x tyre age (+ curvature)   (the degradation we're after)

Fuel and tyre age rise together within a stint, so they can't be told apart there; a pit stop
resets tyre age while the lap count keeps going, and that is what separates them.
"""
import numpy as np
import pandas as pd

from .data import DRY

COMPOUNDS = DRY
REF = "HARD"                      # compound offsets are measured against the hard tyre


def design(c: pd.DataFrame, curvature: bool = True):
    """Columns: one per driver (pace), lap (fuel), offsets for non-reference compounds,
    wear per compound (and wear^2 if curvature)."""
    drivers = sorted(c["driver"].unique())
    cols, X = [], []
    for dv in drivers:
        X.append((c["driver"] == dv).to_numpy(float)); cols.append(f"pace_{dv}")
    X.append(c["lap"].to_numpy(float)); cols.append("fuel")
    for k in COMPOUNDS:
        on = (c["compound"] == k).to_numpy(float)
        if k != REF:
            X.append(on); cols.append(f"offset_{k}")
        X.append(on * c["tyre_age"].to_numpy(float)); cols.append(f"wear_{k}")
        if curvature:
            X.append(on * c["tyre_age"].to_numpy(float) ** 2 / 100); cols.append(f"curve_{k}")
    return np.column_stack(X), cols


def fit_race(c: pd.DataFrame, ridge: float = 1.0, curvature: bool = True, prior: dict | None = None) -> dict:
    """Least squares with a ridge on everything except driver pace, pulling each estimate toward
    `prior` (typical values from other races) or toward zero if no prior is given. A compound
    that was barely used then stays near its typical value instead of blowing up. Seconds."""
    X, cols = design(c, curvature)
    y = c["lap_time"].to_numpy(float)
    pen = np.array([0.0 if k.startswith("pace_") else ridge for k in cols])
    b0 = np.array([0.0 if k.startswith("pace_") else (prior or {}).get(k, 0.0) for k in cols])
    beta = np.linalg.solve(X.T @ X + np.diag(pen), X.T @ y + pen * b0)
    p = dict(zip(cols, beta))
    used = c["compound"].value_counts()
    out = {"fuel": p["fuel"], "laps_used": len(c), "drivers": c["driver"].nunique()}
    for k in COMPOUNDS:
        out[f"offset_{k}"] = p.get(f"offset_{k}", 0.0) if k != REF else 0.0
        out[f"wear_{k}"] = p[f"wear_{k}"]
        out[f"curve_{k}"] = p.get(f"curve_{k}", 0.0)
        out[f"laps_{k}"] = int(used.get(k, 0))
    resid = y - X @ beta
    out["rmse"] = float(np.sqrt(np.mean(resid ** 2)))
    return out


PARAMS = ["fuel"] + [f"{p}_{k}" for k in COMPOUNDS for p in ("offset", "wear", "curve")]


def fit_all(c: pd.DataFrame, prior: dict | None = None, **kw) -> pd.DataFrame:
    rows = []
    for (rid, year, race), g in c.groupby(["race_id", "year", "race"], sort=False):
        if g["compound"].nunique() < 2 or len(g) < 200:
            continue
        r = fit_race(g, prior=prior, **kw)
        r.update(race_id=rid, year=year, race=race, track_temp=g["track_temp"].median(),
                 total_laps=int(g["total_laps"].iloc[0]))
        rows.append(r)
    return pd.DataFrame(rows)


def loss_after(params: dict, compound: str, age: np.ndarray) -> np.ndarray:
    """Seconds lost to tyre wear after `age` laps on `compound`, relative to a new tyre."""
    w, q = params[f"wear_{compound}"], params[f"curve_{compound}"]
    return w * age + q * age ** 2 / 100
