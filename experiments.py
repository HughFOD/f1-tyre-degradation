"""Re-runs the improvement ideas described in the README ("What I tried") and the noise-floor
analysis. Needs the lap data from run.py first. About 5 minutes.

    python experiments.py
"""
import json

import pandas as pd

from run import MIN_GAP, RIDGE, TRACK_K
from tyres import data, experiments, forecast

if __name__ == "__main__":
    out = data.ROOT / "output"
    d = data.add_gap(data.load())
    c = data.clean_laps(d, min_gap=MIN_GAP)
    params = pd.read_csv(out / "wear_by_race.csv")
    params["track"] = [forecast.track(a, b) for a, b in zip(params["race"], params["year"])]
    hold = pd.read_csv(out / "stint_forecasts_holdout.csv")
    runs = pd.read_csv(out / "long_runs.csv")

    res = {
        "temperature (2019-2023)": experiments.temperature(params).round(3).to_dict("records"),
        "team or driver wear": experiments.team_wear(c, RIDGE, TRACK_K),
        "robust planning (2023)": experiments.robust_planning(d, c, RIDGE, TRACK_K).round(2).to_dict("records"),
        "stint limits from track history (2023)": experiments.stint_caps(d, c, RIDGE, TRACK_K).round(2).to_dict("records"),
        "practice in the pit plans (2023)": experiments.practice_in_strategy(d, c, runs, RIDGE, TRACK_K).round(2).to_dict("records"),
        "new tracks (2024-26)": experiments.new_tracks(hold).round(3).to_dict("records"),
        "practice session weights": experiments.session_weights(
            pd.read_csv(out / "stint_forecasts_validation.csv"), hold),
        "Pirelli compound choices": experiments.pirelli_compounds(c, runs, params, RIDGE, TRACK_K),
        "noise floor (2024-26)": experiments.noise_floor(hold),
    }
    (out / "experiments.json").write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps(res, indent=2, default=float))
