"""Runs everything: download, tidy, fit, test, charts. Results go to output/ and docs/img/.

    python run.py            (first run downloads ~60 MB of lap data from GitHub)
"""
import json
import time

import numpy as np
import pandas as pd

from tyres import data, forecast, model, report, strategy

# Chosen on 2023 only (validation). 2024-2026 is the holdout.
MIN_GAP = 2.0      # seconds behind the car ahead for a lap to count as clean air
RIDGE = 300        # how strongly a race's estimates are pulled toward typical values
TRACK_K = 0.3      # how much a track's own history is trusted vs the typical race
VALIDATION, HOLDOUT = [2023], [2024, 2025, 2026]


def main():
    t0 = time.time()
    out = data.ROOT / "output"
    img = data.ROOT / "docs" / "img"
    out.mkdir(exist_ok=True)
    img.mkdir(parents=True, exist_ok=True)

    print("1/4 Lap data ...")
    data.download()
    d = data.add_gap(data.build())
    c = data.clean_laps(d, min_gap=MIN_GAP)
    print(f"    {d['race_id'].nunique()} races, {len(d):,} laps, {len(c):,} clean-air laps")

    print("2/4 Wear: every race fitted, then forecast from earlier races ...")
    glob = forecast.typical(model.fit_all(c, ridge=1.0))
    params = forecast.race_params(c, glob, RIDGE)
    params.to_csv(out / "wear_by_race.csv", index=False)
    summary = {}
    for name, yrs in (("validation", VALIDATION), ("holdout", HOLDOUT)):
        w = forecast.walk_forward(c, yrs, RIDGE, TRACK_K)
        w.to_csv(out / f"stint_forecasts_{name}.csv", index=False)
        summary[f"stint_{name}"] = forecast.score(w).round(3).to_dict("records")
        if name == "holdout":
            report.forecast_errors(w, img / "stint_forecast_error.png")
            summary["stint_holdout_by_compound"] = {
                k: forecast.score(g).set_index("forecast")["MAE (s per 20 laps)"].round(3).to_dict()
                for k, g in w.groupby("compound")}
    live = forecast.walk_forward_live(c, VALIDATION, RIDGE, TRACK_K)
    summary["live_update_validation"] = {f: round(float(((live[f] - live["slope"]).abs() * 19).mean()), 3)
                                         for f in ("typical", "track_history", "live")}

    print("3/4 Strategy: pre-race plan vs hindsight vs the winner ...")
    for name, yrs in (("validation", VALIDATION), ("holdout", HOLDOUT)):
        e = strategy.evaluate(d, c, yrs, RIDGE, TRACK_K)
        e.to_csv(out / f"strategy_{name}.csv", index=False)
        sc = e["sc_share"] > 0
        summary[f"strategy_{name}"] = {
            "dry races": len(e),
            "plan cost vs hindsight best, median s": round(float(e["plan_cost"].median()), 1),
            "plan cost, mean s": round(float(e["plan_cost"].mean()), 1),
            "stops match hindsight": round(float((e["plan_stops"] == e["hindsight_stops"]).mean()), 2),
            "stops match winner": round(float((e["plan_stops"] == e["winner_stops"]).mean()), 2),
            "hindsight stops match winner": round(float((e["hindsight_stops"] == e["winner_stops"]).mean()), 2),
            "first stop, model minus winner, mean laps": round(float((e["plan_first_stop"] - e["winner_first_stop"]).mean()), 1),
            "plan starts on soft": round(float(e["plan"].str.startswith("S").mean()), 2),
            "winner started on soft": round(float(e["winner_plan"].str.startswith("S").mean()), 2),
            "races with SC/VSC": int(sc.sum()),
            "winner 2+ stops, with SC": round(float((e.loc[sc, "winner_stops"] >= 2).mean()), 2),
            "winner 2+ stops, no SC": round(float((e.loc[~sc, "winner_stops"] >= 2).mean()), 2),
        }
        if name == "holdout":
            report.first_stops(e, img / "first_stop.png")

    print("4/4 Charts ...")
    report.wear_curves(c, d.loc[(d["year"] == 2024) & (d["race"] == "Bahrain Grand Prix"), "race_id"].iloc[0],
                       img / "wear_curves_bahrain_2024.png")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    print(f"\nDone in {time.time() - t0:.0f}s. See output/summary.json")
    return summary


if __name__ == "__main__":
    main()
