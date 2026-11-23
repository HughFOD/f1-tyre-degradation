"""Download race lap times from TracingInsights (one GitHub repo per season) and tidy them into
one table: one row per driver per lap, with tyre compound, tyre age, stint, pit flags, track
status and track temperature."""
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LAPS = ROOT / "data" / "laps.csv.gz"
OTHER = ROOT / "data" / "practice_sprint_laps.csv.gz"
SEASONS = range(2018, 2027)
FILES = ("session_laptimes.json", "session_info.json")
SESSIONS = {"Race": "R", "Sprint": "S", "Practice 1": "FP1", "Practice 2": "FP2", "Practice 3": "FP3"}
DRY = ("SOFT", "MEDIUM", "HARD")


def download(seasons=SEASONS, raw: Path = RAW) -> None:
    """Sparse-clone only the lap and info files of each race weekend's practice, sprint and race
    sessions (about 16 MB a season)."""
    raw.mkdir(parents=True, exist_ok=True)
    for y in seasons:
        dest = raw / str(y)
        if not dest.exists():
            subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse",
                            f"https://github.com/TracingInsights/{y}", str(dest)], check=True)
            subprocess.run(["git", "sparse-checkout", "set", "--no-cone",
                            *[f"/*/{s}/{f}" for s in SESSIONS for f in FILES]], cwd=dest, check=True)
        else:
            subprocess.run(["git", "pull", "-q", "--depth", "1"], cwd=dest, check=False)


def _flag(v) -> bool:
    return v not in (None, "None", "", False, "False") and not (isinstance(v, float) and np.isnan(v))


def _race(folder: Path, year: int, session: str = "R") -> pd.DataFrame:
    s = json.loads((folder / "session_laptimes.json").read_text())
    info = json.loads((folder / "session_info.json").read_text())
    d = pd.DataFrame({k: s[k] for k in ("drv", "team", "lap", "time", "compound", "stint", "life", "fresh",
                                         "pos", "status", "pin", "pout", "iacc", "del", "sesT", "wTT")})
    d["pit_in"] = d.pop("pin").map(_flag)
    d["pit_out"] = d.pop("pout").map(_flag)
    d["accurate"] = d.pop("iacc").map(lambda v: str(v) == "True")
    d["deleted"] = d.pop("del").map(lambda v: str(v) == "True")
    d["fresh"] = d["fresh"].map(lambda v: str(v) == "True")
    for c in ("time", "lap", "stint", "life", "pos", "sesT", "wTT"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["status"] = d["status"].astype(str)
    d = d.rename(columns={"drv": "driver", "time": "lap_time", "life": "tyre_age", "wTT": "track_temp",
                          "sesT": "session_time"})
    d["year"] = year
    d["session"] = session
    d["race"] = folder.parent.name
    d["date"] = pd.to_datetime(info.get("t0_date", f"{year}-01-01")).normalize()
    d["total_laps"] = info.get("total_laps") or d["lap"].max()
    return d


def build(raw: Path = RAW, out: Path = LAPS) -> pd.DataFrame:
    parts = []
    for y in SEASONS:
        for f in sorted((raw / str(y)).glob("*/Race/session_laptimes.json")):
            try:
                parts.append(_race(f.parent, y))
            except Exception as e:       # a handful of files are incomplete
                print(f"  skipped {y} {f.parent.parent.name}: {type(e).__name__}")
    d = pd.concat(parts, ignore_index=True)
    order = d[["year", "race", "date"]].drop_duplicates().sort_values("date")
    order["round"] = order.groupby("year").cumcount() + 1
    d = d.merge(order[["year", "race", "round"]], on=["year", "race"])
    d["race_id"] = d["year"].astype(str) + "-" + d["round"].astype(str).str.zfill(2)
    d = d.sort_values(["date", "driver", "lap"]).reset_index(drop=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(out, index=False)
    return d


def build_other(race_laps: pd.DataFrame, raw: Path = RAW, out: Path = OTHER) -> pd.DataFrame:
    """Practice and sprint laps, tagged with the race weekend they belong to (same race_id as
    that weekend's Grand Prix). Weekends whose race isn't in race_laps are dropped."""
    ids = race_laps[["year", "race", "race_id", "round"]].drop_duplicates()
    parts = []
    for y in SEASONS:
        for folder_name, tag in SESSIONS.items():
            if tag == "R":
                continue
            for f in sorted((raw / str(y)).glob(f"*/{folder_name}/session_laptimes.json")):
                try:
                    parts.append(_race(f.parent, y, tag))
                except Exception as e:
                    print(f"  skipped {y} {f.parent.parent.name} {tag}: {type(e).__name__}")
    d = pd.concat(parts, ignore_index=True).merge(ids, on=["year", "race"])
    d = d.sort_values(["date", "session", "driver", "lap"]).reset_index(drop=True)
    d.to_csv(out, index=False)
    return d


def load(path: Path = LAPS) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["date"], dtype={"status": str})


def long_runs(o: pd.DataFrame, min_laps: int = 5, within: float = 0.03) -> pd.DataFrame:
    """Practice/sprint stints that look like race running: green-flag, accurate, dry laps that
    aren't in- or out-laps, within 3% of the stint's median lap (drops push laps and cool-down
    laps), at least `min_laps` of them. One row per run with its lap-time trend (s/lap)."""
    m = ((o["status"] == "1") & o["compound"].isin(DRY) & ~o["pit_in"].astype(bool) & ~o["pit_out"].astype(bool)
         & o["accurate"].astype(bool) & ~o["deleted"].astype(bool) & o["lap_time"].notna() & o["tyre_age"].notna())
    c = o[m].copy()
    med = c.groupby(["race_id", "session", "driver", "stint"])["lap_time"].transform("median")
    c = c[(c["lap_time"] - med).abs() <= within * med]
    rows = []
    for (rid, ses, drv, st), g in c.groupby(["race_id", "session", "driver", "stint"], sort=False):
        if len(g) < min_laps or g["compound"].nunique() != 1:
            continue
        rows.append(dict(race_id=rid, session=ses, driver=drv, team=g["team"].iloc[0], stint=st,
                         compound=g["compound"].iloc[0], age0=g["tyre_age"].min(), age1=g["tyre_age"].max(),
                         laps=len(g), slope=np.polyfit(g["lap"].to_numpy(float), g["lap_time"].to_numpy(float), 1)[0]))
    return pd.DataFrame(rows)


def add_gap(d: pd.DataFrame) -> pd.DataFrame:
    """Seconds behind the car one place ahead when crossing the line at the end of the lap."""
    ahead = d[["race_id", "lap", "pos", "session_time"]].rename(columns={"session_time": "t_ahead"})
    ahead = ahead.assign(pos=ahead["pos"] + 1).drop_duplicates(["race_id", "lap", "pos"])
    d = d.merge(ahead, on=["race_id", "lap", "pos"], how="left")
    d["gap_ahead"] = (d["session_time"] - d["t_ahead"]).where(d["pos"] > 1, np.inf)
    return d.drop(columns="t_ahead")


def clean_laps(d: pd.DataFrame, min_gap: float | None = 2.0) -> pd.DataFrame:
    """Laps that measure pace: green flag the whole lap, dry tyres, not lap 1, not in/out laps,
    timing marked accurate, not deleted, within 7% of the driver's typical lap that race (drops
    spins and damage), and, if min_gap is set, in clean air: at least min_gap seconds behind the
    car ahead at the end of the lap and of the lap before (a car stuck in a queue can't show its
    real pace, and queues are worst early in the race when the soft tyres are on)."""
    if "gap_ahead" not in d:
        d = add_gap(d)
    m = ((d["status"] == "1") & d["compound"].isin(DRY) & (d["lap"] > 1) & ~d["pit_in"] & ~d["pit_out"]
         & d["accurate"] & ~d["deleted"] & d["lap_time"].notna() & d["tyre_age"].notna())
    if min_gap is not None:
        prev = d.groupby(["race_id", "driver"])["gap_ahead"].shift(1)
        m &= (d["gap_ahead"] >= min_gap) & (prev.fillna(np.inf) >= min_gap)
    c = d[m].copy()
    med = c.groupby(["race_id", "driver"])["lap_time"].transform("median")
    return c[c["lap_time"] < med * 1.07].copy()
