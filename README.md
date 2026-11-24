# F1 tyre degradation

**Website: https://hughod.com/f1-tyre-degradation/** (pick a track to see its wear curves and pit plans)

**Result:** forecasting how much time a stint will lose to tyre wear, using earlier races plus that weekend's practice running, gets within **0.95 s per 20-lap stint** on 1,635 stints from 2024 to November 2026, against 1.46 s if tyre wear is ignored. A pre-race pit plan built on those forecasts picks the right number of stops in 84% of dry races (judged against the best plan in hindsight). But it costs a median 7.8 s against that best plan, mostly because it trusts the soft tyre far more than teams do. Each forecast also comes with a range, and the README checks honestly how often those ranges hold. It also explains why the plans fall short, including twelve ideas tested to close the gap and which ones held up.

![Tyre wear at Monza and in Hungary, 2026](docs/img/wear_monza_vs_hungary_2026.png)

*Same cars, same season. At Monza the tyres lose about half a second over 50 laps; in Hungary they lose 2-3 seconds within 30. Each dot is a clean-air lap with fuel burn and the driver's pace taken out; lines are the fitted wear curves (compounds with fewer than 150 clean laps aren't drawn). In Hungary the compounds don't wear in the expected order. That's one of the model's weak spots, covered under Findings.*

Every lap of a race, the car gets lighter as fuel burns (faster) and its tyres wear (slower). Untangling the two tells you how fast each compound degrades at each track, and from that, when to pit and on which tyres. This project measures tyre wear lap by lap in every Grand Prix since 2018, tests whether it can be forecast before a race, and tests whether those forecasts lead to good pit strategies.

## The data

Lap-by-lap timing for every race weekend from 2018 to November 2026 (lap time, tyre compound and age, stint, pit flags, track status, position, track temperature):

- **192 Grands Prix**, 212,182 laps. 83,800 of them are clean-air laps that show real pace (see below).
- **5,369 long runs** from practice (FP1-FP3) and sprint races: stretches of 5+ race-pace laps on one set of tyres, which is how teams rehearse the race on Friday. That includes 1,921 runs on softs, against only about 250 soft stints in races.
- **Pirelli's compound choice for 173 races (2019-2026)**: which rubber (C0 to C6) was the hard, medium and soft at each race, in `data/compounds.csv` with a source for every row. Most rows come from a list compiled with sources in [MisterKinn/f1-data-analyst](https://github.com/MisterKinn/f1-data-analyst/pull/127), spot-checked against seven Pirelli announcements (all matched). The two missing 2026 races (Las Vegas; the Bahrain GP relocated to Sepang) were added from Pirelli and Formula 1.

## The idea

**One equation per race.** Every clean lap is explained as:

> lap time = driver's pace that race + fuel effect × lap number + compound offset + wear(compound, tyre age)

Wear is a curve (linear plus a bend), fitted separately for soft, medium and hard.

**How fuel and wear are told apart.** Within a stint, tyre age and lap number go up together, one lap at a time, so the two effects can't be separated there. A pit stop resets tyre age while the lap count keeps going. Because drivers pit on different laps, each race contains enough of those resets to separate the two. (An automated test confirms that if every driver pitted on the same lap, the model could not tell them apart.) The fitted fuel effect comes out at **−0.06 s per lap** (median over races), which is in the physically expected range.

**Only laps that show real pace.** Left out:
- laps under safety car, virtual safety car or yellow flags
- lap 1, in-laps and out-laps
- wet tyres
- laps the timing system flags as inaccurate
- spins (more than 7% off the driver's typical lap)
- **laps in traffic**: any lap finished less than 2 s behind the car ahead, on that lap or the one before

The traffic filter matters. Without it the soft tyre looks slower than it is, because softs are mostly used at the start, when cars are queued behind each other.

**Pulling noisy estimates toward typical values.** A compound used for only a handful of laps can produce wild numbers, so each race's estimates are pulled toward what is typical, more strongly when there is less data.

**The forecast for a race** starts from that track's earlier races (recent years count more), blended with a typical race. Then it's **shifted by this weekend's practice**: if Friday's long runs lost more time than the forecast expected, the race forecast moves the same way, more so when there were more runs.

## How it is tested

Everything is **walk-forward**: each race is forecast from races that happened before it (plus that weekend's practice, which happens before the race), never from the race itself or later ones. An automated test checks this. Every setting (the traffic threshold, how strongly to pull toward typical, how much to trust a track's history, how much to trust practice) was chosen on **2023** only. The numbers below are for **2024 to November 2026**, which played no part in those choices.

**Test 1, wear:** for each stint of 8+ clean laps, how much lap time did it actually gain or lose from start to finish, and how close was the forecast? The error is scaled to a 20-lap stint so it reads in seconds.

**Test 2, strategy:** for each dry race, take the fastest one- or two-stop plan under the pre-race forecast (using that track's typical pit-lane time loss, measured from earlier races). Then score it using the wear the race actually showed, against the best plan in hindsight.

## Findings (2024 to November 2026)

### Forecasting wear

| Forecast | Error, s per 20-lap stint |
|---|---:|
| Ignore tyre wear (fuel only) | 1.46 |
| Typical race | 1.00 |
| This track's history | 0.975 |
| **+ this weekend's practice** | **0.950** |
| Hindsight: fit on the race itself (not a forecast) | 0.68 |

![Forecast error by season](docs/img/stint_forecast_error.png)

- **Modelling wear is most of the gain.** Ignoring it misses by half a second more per stint.
- **Practice helps, a little and consistently.** It improves the forecast in every season (2024: 0.950 → 0.915 s, 2025: 0.854 → 0.846, 2026: 1.114 → 1.083) and on every compound. It also removes most of the forecast's tendency to under-predict wear (bias −0.21 → −0.09 s). Race by race the gain isn't certain yet (95% interval −0.01 to +0.04 s per race; 60% of races improve).
- **Track history barely beats a typical race on 2024-26** (0.975 vs 1.00), and race by race the difference isn't distinguishable from zero. In 2023 it helped clearly (0.78 vs 0.92). Conditions on the day matter more than a track's past, which is why that weekend's practice adds something.
- **Most of what's left can't be forecast.** Stints that should behave the same (same race, same compound, tyre ages within 3 laps at both ends: 2,063 pairs) still differ by about **0.60 s** per 20 laps each, and teammates in the same car by 0.62 s. That's how hard each driver pushes, traffic and tyre management. Hindsight (0.68 s) is already close to that floor (the red line in the chart), so of the forecast's 0.95 s, only about a third is left to win with better information.
- **Softs are hardest** (1.42 s error vs 0.80 s for hards). They're raced least and in the shortest stints.
- **2026 is the worst year** (1.08 s). New cars and tyres arrived, and history from the old cars fits them less well.
- **New tracks are hard, and practice doesn't rescue them.** On the three tracks with no history (Las Vegas 2024, Madrid 2026, and the 2026 Bahrain GP that was moved to Sepang in Malaysia; 67 stints) the error is 1.40 s, and practice makes it slightly worse (1.43 s): the surface changes too much over a new track's first weekend.
- **Pirelli's compound choice adds nothing to the forecast, and that's informative.** Softer rubber doesn't wear faster across races: in the 18-inch era (2022-25) a C1 lost a median 1.47 s after 20 laps and a C5 0.78 s. Pirelli brings soft compounds to gentle tracks and hard ones to tough tracks, so "hard, medium, soft" are already balanced to behave alike at each circuit. Forecasting each compound from the same rubber's history at that track (rather than the same label) was slightly *worse*, including at the races where Pirelli changed compounds from the previous visit (9 in 2023: 0.80 → 0.82 s; 14 in 2024-26: 1.08 → 1.11 s).

### How sure is each forecast?

Every stint forecast comes with an 80% range: how much faster or slower the stint might go, built from how far off earlier seasons' forecasts were on the same compound (2024's ranges come from 2023's misses, 2025's from 2023-24, and so on, so no range sees its own season). An 80% range is about 2.4 s wide over a 20-lap stint.

**They hold 74% of the time, not 80%:**
- **By season:** 68% in 2024, 79% in 2025, 74% in 2026. Later seasons have mostly been harder to forecast than the ones their ranges were built from.
- **By compound:** softs hold only 67%. Softs are raced least, so their earlier misses understate how wrong a soft forecast can be.

Widening the ranges to hit 80% on these seasons would mean tuning on the test seasons, so they're reported as they came out: treat them as roughly 75% ranges.

### Pit strategy (61 dry races)

| | |
|---|---:|
| Pre-race plan uses the same number of stops as the best plan in hindsight | 84% |
| ... as the race winner | 64% |
| Best plan in hindsight uses the same number of stops as the winner | 66% |
| Time the pre-race plan loses vs the best plan in hindsight (median) | 7.8 s |
| Pre-race plans that start on softs / winners that started on softs | 75% / 15% |

- **Number of stops: nearly as good as it gets with this approach.** The pre-race plan agrees with the winner about as often as the hindsight-best plan does (64% vs 66%). The remaining disagreement comes from things lap times don't show: track position, undercuts, safety cars.
- **Tyre choice is the weak spot.** The model starts most races on softs; winners almost never do. In race trim, new softs, mediums and hards come out within about a tenth of a second of each other in this data, not even in the expected order. So the model rarely sees a reason to avoid the soft's faster wear, while teams know softs also grain, overheat and fall off a cliff. Those effects show up as lost track position, not in clean-air lap times.
- **Safety cars.** 45 of the 61 dry races had a safety car or VSC. In those, the winner stopped twice or more 49% of the time, against 31% without one. A stop under a safety car costs about half as much, but building expected safety cars into the planning didn't change its choices (see below): the gain comes from reacting when one happens. (In 2023 the difference didn't appear, so treat it as suggestive.)

![First stop: model vs winner](docs/img/first_stop.png)

## What I tried to improve it

Twelve ideas, all reproducible with `python experiments.py` (results in `output/experiments.json`). Each was judged on 2023 first; anything that helped there was then scored on 2024-2026.

| Idea | Result |
|---|---|
| **More data: the 2018 season** | Kept. Forecasts about the same (0.972 → 0.975 s); pit plans better (median time lost 9.5 → 7.8 s, stops match hindsight 82% → 84%). |
| **More data: practice and sprint long runs** (shift the forecast by this weekend's running) | **Kept.** 0.975 → 0.950 s on 2024-26, better in every season and compound. |
| **More data: Pirelli's compound choices** (forecast each compound from the same rubber's history, not the same label) | No. Slightly worse everywhere, including where Pirelli changed compounds (see Findings): Pirelli balances its choices so the labels already behave consistently. |
| **Weight practice sessions differently**: FP2 race simulations and sprints count more? | No meaningful gain. The best 2023 setting drops FP3 (qualifying preparation), but on 2024-26 it changes the error by about 0.001 s (2026 got slightly worse). All sessions count equally. |
| **Track temperature**: hotter race, more wear? | No. At the same track, hotter races showed no more wear (correlation −0.02 to −0.27 by compound, 2019-2023, the wrong direction). |
| **Team or driver wear**: some cars are easier on tyres | Helped a little on 2023 (0.78 → 0.75 s), nothing on 2024-26 (0.975 → 0.971 s). Car-to-car differences within a race are mostly the same noise as teammate-to-teammate. |
| **Watch the race**: re-fit wear on the first 40% of the race | Worse (0.78 → 0.94 s on 2023). Early laps on heavy fuel, a green track and managed pace mislead about later stints. |
| **Plan for the race as it might go**: average over simulated races, with wear varied as much as it has year to year and safety cars as often as they've happened at each track | Passed 2023 once the 2018 data was added (median time lost 8.1 → 4.7 s), then **failed on 2024-26** (10.6 vs 10.2 s median, 14.6 vs 14.8 s mean; per race −0.8 to +0.2 s). The 2023 gain was luck. Not adopted. |
| **Practice in the pit plans** | Shifting all compounds: no change. Using each compound's own practice running: plans pit when winners do (first stop within 0.5-3 laps of the winner's), but the lap-time model scores them much slower (mean 15-18 s). Not adopted. |
| **Only plan stints as long as teams have run them at that track** | A trade-off. Plans get closer to the winners' (same number of stops 40% → 60%, first stop 9.1 → 3.8 laps closer) but score 3.8 → 8.4 s slower on lap time. |
| **Similar tracks for new circuits** | Not built: only 67 holdout stints (4%) are on tracks with no history, and 7 in 2023 to tune on, too few to do it honestly. |
| **Practice to fix the soft tyre** | No. Even with 1,921 soft long runs, plans still start on softs (60-65% on 2023). |

The pattern in the last rows is the heart of the project. Whenever data pulls the plans toward what teams actually do, the lap-time model calls the result slower. The teams are seeing things clean-air lap times don't contain: track position, undercuts, graining, tyre cliffs. A model built only on lap times can't tell who's right, so scoring it against itself flatters it.

## What would make it better

1. **Model track position and undercuts.** Plans should be scored on finishing position, not clean-air race time, which is what teams actually optimise.
2. **The soft tyre's cliff and graining.** Use how and when stints *ended* (pit calls after a sudden drop-off) as well as average wear.
3. **Pirelli's track ratings** (asphalt abrasion, tyre stress, traction), published before each race. They would help most on new tracks, where there's no history to lean on; so far they've only been collected in machine-readable form for 2025-26, too few seasons to learn from.

## Run it

In PyCharm, open each file and click the green ▶ arrow:

1. `step1_setup.py`: one time, creates `.venv` and installs packages
2. `step2_run_analysis.py`: downloads the lap data (first time about 140 MB from GitHub), fits every race, runs both tests, writes `output/` and the charts (about 3 minutes)
3. `step3_run_tests.py`: the automatic checks

Or from a terminal: `python run.py`, then `python experiments.py` to re-run the improvement tests (about 4 minutes).

## Files

| | |
|---|---|
| `tyres/data.py` | download, tidy, gap to the car ahead, clean-lap filter, practice/sprint long runs |
| `tyres/model.py` | the per-race lap-time model (fuel, compound offset, wear) |
| `tyres/forecast.py` | forecasting wear from earlier races and the weekend's practice, the stint test, forecast ranges, and the rubber-matching experiment |
| `data/compounds.csv` | Pirelli's hard / medium / soft compound for 173 races, with sources |
| `tyres/strategy.py` | pit-lane time loss, plan search, and the strategy tests |
| `tyres/report.py` | charts |
| `tyres/website.py` | builds the project page, `docs/index.html` |
| `tyres/experiments.py`, `experiments.py` | the improvement ideas above and the noise-floor analysis |
| `output/` | wear for every race, every long run, every stint forecast with its 80% range, every race's plans, `summary.json`, `experiments.json` |

## Data

Lap-by-lap timing 2018-2026 for races, sprints and practice from [TracingInsights](https://github.com/TracingInsights), which archives the official F1 live-timing feed via FastF1. A few 2018-2019 sessions are incomplete in the archive and are skipped. Pirelli compound choices: `data/compounds.csv` (a source for every row; see The data). This project is unofficial and not associated with Formula 1 or Pirelli.
