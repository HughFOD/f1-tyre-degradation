"""Charts for the README."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import model

COL = {"SOFT": "#d7261e", "MEDIUM": "#e8b100", "HARD": "#6b6b6b"}
NAMES = {"fuel_only": "Ignore tyre wear", "typical": "Typical race", "track_history": "This track's history",
         "hindsight": "Hindsight (fit on the race itself)"}


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#e6e6e6", lw=0.8)
    ax.set_axisbelow(True)


def wear_curves(c: pd.DataFrame, race_id: str, path):
    """Lap times with fuel and driver pace taken out, against tyre age, one colour per compound,
    with the fitted wear curves."""
    g = c[c["race_id"] == race_id]
    X, cols = model.design(g)
    beta = np.linalg.lstsq(X, g["lap_time"].to_numpy(float), rcond=None)[0]
    p = dict(zip(cols, beta))
    adj = g["lap_time"] - [p[f"pace_{d}"] for d in g["driver"]] - p["fuel"] * g["lap"]
    fig, ax = plt.subplots(figsize=(8, 4.3))
    for k in model.COMPOUNDS:
        m = g["compound"] == k
        if m.sum() < 30:
            continue
        ax.scatter(g.loc[m, "tyre_age"], adj[m], s=5, alpha=.25, color=COL[k])
        age = np.arange(1, g.loc[m, "tyre_age"].max() + 1)
        off = p.get(f"offset_{k}", 0.0)
        curve = off + p[f"wear_{k}"] * age + p.get(f"curve_{k}", 0) * age ** 2 / 100
        ax.plot(age, curve, color=COL[k], lw=2.5, label=k.title())
    ax.set_ylim(np.percentile(adj, 1) - .3, np.percentile(adj, 99) + .3)
    ax.set_xlabel("Tyre age (laps)")
    ax.set_ylabel("Seconds slower than a new hard tyre")
    r = g.iloc[0]
    ax.set_title(f"{r['year']} {r['race']}: lap times with fuel and driver pace taken out", loc="left", fontsize=11)
    _style(ax)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def forecast_errors(w: pd.DataFrame, path, floor: float | None = None):
    e = {f: ((w[f] - w["slope"]).abs() * 19).groupby(w["year"]).mean() for f in NAMES}
    t = pd.DataFrame(e)
    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(len(t))
    cols = ["#bbbbbb", "#9ec1f0", "#2a6fdb", "#3b3b3b"]
    for i, f in enumerate(NAMES):
        ax.bar(x + (i - 1.5) * .2, t[f], .19, label=NAMES[f], color=cols[i])
    ax.set_xticks(x, t.index.astype(str))
    ax.set_ylim(0, t.to_numpy().max() * 1.3)
    if floor is not None:
        ax.axhline(floor, color="#e4572e", lw=1.2, ls="--")
        ax.text(len(t) - 0.5, floor + 0.03, f"unpredictable part (~{floor:.1f} s): even matched stints differ this much",
                ha="right", va="bottom", fontsize=8, color="#e4572e")
    ax.set_ylabel("Avg error, seconds per 20-lap stint")
    ax.set_title("Forecasting how much time a stint loses (each race forecast from earlier races)", loc="left", fontsize=11)
    _style(ax)
    ax.legend(frameon=False, fontsize=8.5, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def first_stops(e: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(5.2, 5))
    sc = e["sc_share"] > 0
    ax.scatter(e.loc[~sc, "winner_first_stop"], e.loc[~sc, "plan_first_stop"], color="#2a6fdb", label="No safety car")
    ax.scatter(e.loc[sc, "winner_first_stop"], e.loc[sc, "plan_first_stop"], color="#e4572e", label="Safety car or VSC")
    lim = [0, max(e["winner_first_stop"].max(), e["plan_first_stop"].max()) + 3]
    ax.plot(lim, lim, color="#bbbbbb", ls="--", lw=1)
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("Winner's first stop (lap)")
    ax.set_ylabel("Model's planned first stop (lap)")
    ax.set_title("First pit stop: model's pre-race plan vs the winner", loc="left", fontsize=11)
    _style(ax)
    ax.legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def wear_pair(c: pd.DataFrame, low: str, high: str, path):
    """Two races side by side on the same scale: a low-wear and a high-wear track."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3), sharey=True)
    for ax, rid in zip(axes, (low, high)):
        g = c[c["race_id"] == rid]
        X, cols = model.design(g)
        p = dict(zip(cols, np.linalg.lstsq(X, g["lap_time"].to_numpy(float), rcond=None)[0]))
        adj = g["lap_time"] - [p[f"pace_{d}"] for d in g["driver"]] - p["fuel"] * g["lap"]
        for k in model.COMPOUNDS:
            m = g["compound"] == k
            if m.sum() < 150:          # too few clean laps to draw a trustworthy curve
                continue
            ax.scatter(g.loc[m, "tyre_age"], adj[m], s=5, alpha=.25, color=COL[k])
            age = np.arange(1, g.loc[m, "tyre_age"].max() + 1)
            curve = p.get(f"offset_{k}", 0.0) + p[f"wear_{k}"] * age + p.get(f"curve_{k}", 0) * age ** 2 / 100
            ax.plot(age, curve, color=COL[k], lw=2.5, label=k.title())
        r = g.iloc[0]
        ax.set_title(f"{r['year']} {r['race'].replace(' Grand Prix', ' GP')}", loc="left", fontsize=11)
        ax.set_xlabel("Tyre age (laps)")
        _style(ax)
        ax.legend(frameon=False, fontsize=9)
    axes[0].set_ylabel("Seconds slower than a new hard tyre")
    axes[0].set_ylim(-1.5, 4)
    fig.suptitle("Same cars, same year: tyre wear depends on the track (fuel and driver pace taken out)",
                 x=0.01, ha="left", fontsize=11.5)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
