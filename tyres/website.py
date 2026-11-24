"""Builds the project page, docs/index.html, from the files in output/. GitHub Pages serves docs/.
Everything the page shows is computed by run.py and experiments.py; nothing here is typed in by hand
except the explanatory text."""
import json

import pandas as pd

from . import forecast
from .data import ROOT

OUT = ROOT / "output"
DOCS = ROOT / "docs"
REPO = "https://github.com/HughFOD/f1-tyre-degradation"
SITE = "https://hughod.com/f1-tyre-degradation/"


PLACES = {"Abu Dhabi": "Abu Dhabi", "Australian": "Australia", "Austrian": "Austria", "Azerbaijan": "Baku",
          "Bahrain": "Bahrain", "Belgian": "Spa", "British": "Silverstone", "Canadian": "Montreal",
          "Chinese": "Shanghai", "Dutch": "Zandvoort", "Emilia Romagna": "Imola", "Hungarian": "Hungary",
          "Italian": "Monza", "Japanese": "Suzuka", "Las Vegas": "Las Vegas", "Mexico City": "Mexico City",
          "Miami": "Miami", "Monaco": "Monaco", "Qatar": "Qatar", "Saudi Arabian": "Jeddah",
          "Singapore": "Singapore", "Spanish": "Barcelona", "São Paulo": "São Paulo", "United States": "Austin",
          "Portuguese": "Portimão", "French": "Paul Ricard", "Russian": "Sochi", "Turkish": "Istanbul"}


def _track_label(race: str, year: int) -> str:
    t = forecast.track(race, year)
    if t in ("Sepang", "Madrid"):
        return {"Sepang": "Sepang", "Madrid": "Madrid"}[t]
    short = t.replace(" Grand Prix", "")
    return PLACES.get(short, short)


def explorer_data() -> list:
    """The latest dry race at each track in the test seasons: forecast and actual wear, Pirelli's
    compounds, and the three pit plans."""
    e = pd.read_csv(OUT / "strategy_holdout.csv")
    alloc = pd.read_csv(ROOT / "data" / "compounds.csv")
    e["track"] = [_track_label(r, y) for r, y in zip(e["race"], e["year"])]
    e = e.sort_values(["year", "race_id"]).groupby("track").tail(1)
    out = []
    for _, r in e.sort_values("track").iterrows():
        a = alloc[(alloc["year"] == r["year"]) & (alloc["race"] == r["race"])]
        out.append({
            "track": r["track"], "race": r["race"], "year": int(r["year"]), "laps": int(r["laps"]),
            "pit_loss": float(r["pit_loss"]), "safety_car": bool(r["sc_share"] > 0),
            "forecast": json.loads(r["forecast_params"]), "actual": json.loads(r["actual_params"]),
            "clean_laps": json.loads(r["clean_laps"]),
            "pirelli": ({"SOFT": a.iloc[0]["soft"], "MEDIUM": a.iloc[0]["medium"], "HARD": a.iloc[0]["hard"]}
                        if len(a) else None),
            "plans": {"model": r["plan"], "hindsight": r["hindsight_plan"], "winner": r["winner_plan"]},
            "plan_cost": round(float(r["plan_cost"]), 1),
        })
    return out


def stats() -> dict:
    s = json.loads((OUT / "summary.json").read_text())
    x = json.loads((OUT / "experiments.json").read_text())
    w = pd.read_csv(OUT / "stint_forecasts_holdout.csv")
    err = {f: float(((w[f] - w["slope"]).abs() * 19).mean())
           for f in ("fuel_only", "typical", "track_history", "weekend", "hindsight")}
    st = s["strategy_holdout"]
    return {"err": err, "floor": s["noise_floor_holdout"]["unpredictable part, s per 20 laps (all pairs)"],
            "stints": int(len(w)), "ranges": s["ranges_holdout"], "strategy": st,
            "rubber": x["Pirelli compound choices"]["median s lost after 20 laps, by rubber"],
            "races": int(pd.read_csv(OUT / "wear_by_race.csv")["race_id"].nunique()),
            "long_runs": int(len(pd.read_csv(OUT / "long_runs.csv")))}


CSS = r"""
:root{--asphalt:#24282c;--kerb:#2f3439;--line:#434a51;--chalk:#eceeea;--dust:#a3aab1;
--soft:#ee3b2b;--medium:#f4c430;--hard:#f2f3ef;--model:#7cc3ef;
--wide:"Archivo",system-ui,sans-serif}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--asphalt);color:var(--chalk);font:400 17px/1.6 var(--wide);font-stretch:100%}
a{color:var(--chalk);text-decoration-color:var(--dust);text-underline-offset:3px}
a:hover{text-decoration-color:var(--chalk)}
:focus-visible{outline:2px solid var(--medium);outline-offset:3px;border-radius:2px}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px}
.read{max-width:66ch}
header.top{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px 24px;align-items:baseline;padding:22px 0 0;color:var(--dust);font-size:.92rem}
header.top a{color:var(--dust)}
h1,h2,h3{font-stretch:125%;font-weight:800;line-height:1.02;letter-spacing:-.01em;margin:0}
h1{font-size:clamp(2.4rem,6.2vw,4.6rem);margin:56px 0 18px;max-width:13em}
h2{font-size:clamp(1.6rem,3.4vw,2.4rem);margin:0 0 14px}
h3{font-size:1.15rem;margin:0 0 6px}
.lede{font-size:1.2rem;color:var(--dust);margin:0 0 36px;max-width:40em}
p{margin:0 0 1em}
section{padding:96px 0 0}
.muted{color:var(--dust)}
.num{font-variant-numeric:tabular-nums;font-stretch:112%;font-weight:700}

/* explorer */
.explorer{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:28px;align-items:start}
@media (max-width:860px){.explorer{grid-template-columns:1fr}}
.tracks{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 18px}
.tracks button{font:600 .88rem var(--wide);font-stretch:110%;color:var(--dust);background:transparent;border:1px solid var(--line);
border-radius:999px;padding:5px 12px;cursor:pointer}
.tracks button[aria-pressed=true]{color:var(--asphalt);background:var(--chalk);border-color:var(--chalk)}
.tracks button:hover{color:var(--chalk);border-color:var(--dust)}
.tracks button[aria-pressed=true]:hover{color:var(--asphalt)}
.chart{width:100%;height:auto;display:block}
.chart text{fill:var(--dust);font:500 13px var(--wide)}
.chart .grid{stroke:var(--line);stroke-width:1}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin:10px 0 0;font-size:.9rem;color:var(--dust)}
.legend i{display:inline-block;width:22px;height:0;border-top:3px solid var(--dust);vertical-align:middle;margin-right:6px}
.legend i.dash{border-top-style:dashed}
.side h3{font-size:1.5rem}
.side .pirelli{display:flex;gap:6px;margin:12px 0 18px}
.tyre{display:inline-flex;align-items:center;justify-content:center;width:52px;height:52px;border-radius:50%;
border:7px solid;font:800 .85rem var(--wide);font-stretch:112%;background:#16191c;color:var(--chalk)}
.plans{margin:6px 0 0}
.plan{margin:0 0 14px}
.plan .who{display:flex;justify-content:space-between;font-size:.9rem;color:var(--dust);margin:0 0 4px}
.bar{display:flex;height:18px;border-radius:3px;overflow:hidden;background:var(--kerb)}
.bar span{display:block;height:100%;border-right:2px solid var(--asphalt)}
.bar span:last-child{border-right:0}
.note{font-size:.92rem;color:var(--dust)}

/* story charts */
.bars{width:100%;max-width:760px;height:auto;display:block;margin:8px 0 6px}
.bars text{fill:var(--chalk);font:500 14px var(--wide)}
.bars .lab{fill:var(--dust)}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:28px;margin:26px 0 0}
.fact .big{font-size:2.6rem;line-height:1;font-stretch:125%;font-weight:800;margin:0 0 8px;font-variant-numeric:tabular-nums}
.fact p{color:var(--dust);margin:0}
table{border-collapse:collapse;width:100%;max-width:900px;font-size:.96rem}
td,th{padding:12px 14px 12px 0;border-top:1px solid var(--line);vertical-align:top;text-align:left}
th{font-weight:700;width:34%}
td.kept{color:var(--chalk)}td{color:var(--dust)}
.verdict{display:inline-block;font-weight:700;color:var(--chalk);margin-right:6px}
footer{margin:110px 0 48px;padding-top:18px;border-top:1px solid var(--line);color:var(--dust);font-size:.92rem}
@media (prefers-reduced-motion:no-preference){.chart path.curve{transition:d .5s ease}}
"""


JS = r"""
const DATA = __DATA__;
const COL = {SOFT:'var(--soft)', MEDIUM:'var(--medium)', HARD:'var(--hard)'};
const COMP = ['SOFT','MEDIUM','HARD'];
const AGE = 40;

function loss(p, c, a){ return p['wear_'+c]*a + p['curve_'+c]*a*a/100; }
function curve(p, c){
  // wear never goes down with age (same rule the pit-plan search uses)
  let out=[], m=0;
  for(let a=0;a<=AGE;a++){ m=Math.max(m, loss(p,c,a), 0); out.push([a,m]); }
  return out;
}
function el(tag, attrs, parent){
  const e=document.createElementNS('http://www.w3.org/2000/svg',tag);
  for(const k in attrs) e.setAttribute(k, attrs[k]); if(parent) parent.appendChild(e); return e;
}
function draw(t){
  const svg=document.getElementById('curves'); svg.innerHTML='';
  const W=Math.max(300, Math.round(svg.parentNode.clientWidth||720)), H=W<560?Math.round(W*0.78):380, L=46,R=12,T=14,B=44;
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const series=[];
  for(const c of COMP){
    series.push({c, kind:'forecast', pts:curve(t.forecast,c)});
    if(t.clean_laps[c]>=100) series.push({c, kind:'actual', pts:curve(t.actual,c)});
  }
  let ymax=Math.max(2, ...series.flatMap(s=>s.pts.map(p=>p[1])));
  ymax=Math.min(Math.ceil(ymax), 8);
  const x=a=>L+(W-L-R)*a/AGE, y=v=>T+(H-T-B)*(1-Math.min(v,ymax)/ymax);
  for(let v=0; v<=ymax; v++){
    el('line',{x1:L,x2:W-R,y1:y(v),y2:y(v),class:'grid'},svg);
    el('text',{x:L-10,y:y(v)+4,'text-anchor':'end'},svg).textContent=v+' s';
  }
  for(let a=0;a<=AGE;a+=10) el('text',{x:x(a),y:H-B+22,'text-anchor':'middle'},svg).textContent=a;
  el('text',{x:(L+W-R)/2,y:H-6,'text-anchor':'middle'},svg).textContent='Laps on the tyre';
  for(const s of series){
    const d=s.pts.map((p,i)=>(i?'L':'M')+x(p[0]).toFixed(1)+','+y(p[1]).toFixed(1)).join('');
    el('path',{d, fill:'none', stroke:COL[s.c], 'stroke-width':s.kind==='actual'?3.2:2,
      'stroke-dasharray':s.kind==='forecast'?'7 6':'', class:'curve', opacity:s.kind==='forecast'?0.85:1},svg);
  }
  svg.setAttribute('aria-label', `Time lost to tyre wear at ${t.track} ${t.year}: forecast and actual, by compound`);
}
function bar(plan, laps){
  const wrap=document.createElement('div'); wrap.className='bar';
  for(const part of plan.split(' > ')){
    const c={S:'SOFT',M:'MEDIUM',H:'HARD'}[part[0]], n=+part.slice(1);
    const s=document.createElement('span'); s.style.width=(100*n/laps)+'%'; s.style.background=COL[c];
    s.title=`${c.toLowerCase()} for ${n} laps`; wrap.appendChild(s);
  }
  return wrap;
}
function words(plan){
  const parts=plan.split(' > ').map(p=>({S:'soft',M:'medium',H:'hard'}[p[0]])+' '+p.slice(1));
  const stops=parts.length-1;
  return `${stops} stop${stops===1?'':'s'}: `+parts.join(', ');
}
function side(t){
  const s=document.getElementById('side');
  const tyres = t.pirelli ? COMP.map(c=>`<span class="tyre" style="border-color:${COL[c]}" title="${c.toLowerCase()} was ${t.pirelli[c]}">${t.pirelli[c]}</span>`).join('') : '';
  s.innerHTML = `<h3>${t.track} ${t.year}</h3>
    <p class="note">${t.laps} laps. A green-flag pit stop cost ${t.pit_loss.toFixed(0)} s${t.safety_car?'; there was a safety car or VSC':''}.</p>
    ${t.pirelli?`<div class="pirelli" aria-label="Pirelli compounds">${tyres}</div>`:''}
    <div class="plans"></div>
    <p class="note">Scored on how the tyres actually wore that day, the model's plan was ${t.plan_cost.toFixed(1)} s slower than the best plan in hindsight.</p>`;
  const box=s.querySelector('.plans');
  for(const [k,label] of [['model','Model, before the race'],['hindsight','Best plan in hindsight'],['winner','What the winner did']]){
    const d=document.createElement('div'); d.className='plan';
    d.innerHTML=`<div class="who"><span>${label}</span><span>${words(t.plans[k])}</span></div>`;
    d.appendChild(bar(t.plans[k], t.laps)); box.appendChild(d);
  }
}
function pick(i){
  current=i;
  document.querySelectorAll('.tracks button').forEach((b,j)=>b.setAttribute('aria-pressed', i===j));
  draw(DATA[i]); side(DATA[i]);
}
const nav=document.querySelector('.tracks');
DATA.forEach((t,i)=>{ const b=document.createElement('button'); b.type='button'; b.textContent=t.track;
  b.addEventListener('click',()=>pick(i)); nav.appendChild(b); });
let current=Math.max(0, DATA.findIndex(t=>t.track==='Hungary'));
pick(current);
let rt; window.addEventListener('resize',()=>{clearTimeout(rt); rt=setTimeout(()=>draw(DATA[current]),150);});
"""


def _error_bars(st: dict) -> str:
    rows = [("Ignore tyre wear", st["err"]["fuel_only"], "var(--line)"),
            ("Assume a typical race", st["err"]["typical"], "var(--line)"),
            ("This track's history", st["err"]["track_history"], "var(--dust)"),
            ("+ this weekend's practice", st["err"]["weekend"], "var(--model)"),
            ("Hindsight: fitted on the race itself", st["err"]["hindsight"], "#5b636b")]
    W, L, rowh, mx = 760, 300, 46, 1.6
    xs = lambda v: L + (W - L - 70) * v / mx
    out = [f'<svg class="bars" viewBox="0 0 {W} {rowh * len(rows) + 40}" role="img" '
           f'aria-label="Forecast error per 20-lap stint by method">']
    for i, (lab, v, col) in enumerate(rows):
        yy = i * rowh + 10
        out.append(f'<text class="lab" x="0" y="{yy + 20}">{lab}</text>'
                   f'<rect x="{L}" y="{yy + 4}" width="{xs(v) - L:.1f}" height="24" fill="{col}" rx="2"/>'
                   f'<text x="{xs(v) + 8:.1f}" y="{yy + 21}" class="num">{v:.2f} s</text>')
    fx = xs(st["floor"])
    h = rowh * len(rows) + 10
    out.append(f'<line x1="{fx:.1f}" x2="{fx:.1f}" y1="4" y2="{h}" stroke="var(--soft)" stroke-dasharray="4 4"/>'
               f'<text x="{fx + 6:.1f}" y="{h + 22}" fill="var(--soft)" style="fill:var(--soft)">'
               f'{st["floor"]:.2f} s: even matched stints differ this much</text></svg>')
    return "".join(out)


def build() -> str:
    data, st = explorer_data(), stats()
    sg = st["strategy"]
    rg = st["ranges"]
    ideas = [
        ("This weekend's practice long runs", "Kept", "Shifting the forecast by how Friday's race simulations went cut the error from "
         f"{st['err']['track_history']:.3f} to {st['err']['weekend']:.3f} s, better in every season and on every compound."),
        ("One more season of history (2018)", "Kept", "Forecasts about the same; pit plans lost less time (median 9.5 to 7.8 s)."),
        ("Pirelli's compound choices", "Didn't help", "Matching each tyre to the same rubber's history at that track was slightly worse, "
         "because Pirelli already picks compounds so that soft, medium and hard behave alike at every circuit."),
        ("Track temperature", "Didn't help", "At the same track, hotter races showed no more wear."),
        ("Team or driver tyre wear", "Didn't help", "A small gain on 2023 that vanished on 2024 to 2026."),
        ("Watching the first part of the race", "Worse", "Early laps on heavy fuel and a green track mislead about later stints."),
        ("Planning for safety cars and uncertain wear", "Didn't hold up", "Looked better on 2023, no better on 2024 to 2026."),
        ("Practice data in the pit plans", "Trade-off", "Plans pit when winners do, but the lap-time model calls them slower."),
        ("Capping stints at what teams have run", "Trade-off", "Plans look more like the winners', and slower to the model."),
        ("Weighting practice sessions differently", "No change", "About a thousandth of a second."),
    ]
    idea_rows = "".join(f'<tr><th scope="row">{a}</th><td><span class="verdict">{b}.</span>{c}</td></tr>' for a, b, c in ideas)
    body = f"""
<div class="wrap">
<header class="top"><span><a href="https://hughod.com/">Hugh O'Donnell</a></span><span><a href="{REPO}">Code and full write-up on GitHub</a></span></header>

<h1>How fast do Formula 1 tyres wear out?</h1>
<p class="lede">Every lap a car gets lighter as fuel burns and slower as its tyres wear. I separated the two for every Grand Prix
since 2018, then tested whether wear can be forecast before a race and whether that leads to good pit strategy.
Pick a track to see what happened in its latest race.</p>

<div class="tracks" role="group" aria-label="Choose a track"></div>
<div class="explorer">
  <figure style="margin:0">
    <svg id="curves" class="chart" viewBox="0 0 720 380" role="img"></svg>
    <div class="legend"><span><i></i>What happened (fitted on the race)</span><span><i class="dash"></i>Forecast before the race</span>
    <span><i style="border-color:var(--soft)"></i>Soft</span><span><i style="border-color:var(--medium)"></i>Medium</span><span><i style="border-color:var(--hard)"></i>Hard</span></div>
    <figcaption class="note" style="margin-top:8px">Seconds slower than a new tyre, with fuel burn and each driver's pace taken out.
    A compound with too few clean laps in the race has only its forecast drawn.</figcaption>
  </figure>
  <aside id="side" class="side" aria-live="polite"></aside>
</div>

<section id="method" class="read">
<h2>Separating fuel from tyres</h2>
<p>Within a stint, the fuel load falls and the tyres age together, lap after lap, so the two effects can't be told apart.
A pit stop breaks the link: the tyres start again from new while the fuel keeps burning. Because drivers stop on different
laps, every race has enough of those resets to separate them. The fuel effect comes out at about six hundredths of a second
faster per lap, which is what the physics says it should be.</p>
<p>Only laps that show real pace count: no safety cars, no pit laps, no lap 1, and no laps stuck within two seconds of the car
in front. That last filter matters most. Without it the soft tyre looks slow, because softs are used at the start, when
the field is still queued up. That leaves {st['races']} races and {st['long_runs']:,} practice long runs to learn from.</p>
</section>

<section id="forecast">
<div class="read">
<h2>Can wear be forecast before the race?</h2>
<p>For {st['stints']:,} stints from 2024 to November 2026, I forecast how much time each would lose using only earlier races and
that weekend's practice, then compared with what happened. The error below is for a 20-lap stint.</p>
</div>
{_error_bars(st)}
<div class="read">
<p>Modelling wear at all is most of the gain. The red line is the part nobody can forecast: two stints from the same race,
on the same compound and at the same tyre ages still differ by that much, from how hard each driver pushed and from traffic.
Fitting on the race itself gets close to that line, so only about a third of the remaining error could ever be won back.</p>
<p>Each forecast also comes with a range meant to hold 80% of the time. It held {100 * rg['inside 80% range']:.0f}% of the time,
and {100 * rg['by compound']['SOFT']:.0f}% on softs, so read them as roughly three-in-four ranges.</p>
</div>
</section>

<section id="strategy">
<div class="read">
<h2>Why the pit plans fall short</h2>
<p>For each of {sg['dry races']} dry races I took the fastest one or two-stop plan under the pre-race forecast and scored it on how
the tyres really wore that day.</p>
</div>
<div class="facts">
  <div class="fact"><div class="big">{100 * sg['stops match hindsight']:.0f}%</div><p>of plans chose the same number of stops as the best plan in hindsight.</p></div>
  <div class="fact"><div class="big">{100 * sg['stops match winner']:.0f}%</div><p>matched the winner, about as often as the hindsight plan itself ({100 * sg['hindsight stops match winner']:.0f}%).</p></div>
  <div class="fact"><div class="big">{100 * sg['plan starts on soft']:.0f}%</div><p>of plans start on softs. Only {100 * sg['winner started on soft']:.0f}% of winners did.</p></div>
</div>
<div class="read" style="margin-top:28px">
<p>The soft tyre is the weak spot. In clean-air lap times, new softs are barely quicker than hards, so the model sees little
reason to avoid them. Teams know softs also grain, overheat and drop off a cliff, which costs track position rather than lap time.
Whenever extra data nudged the plans toward what teams actually do, the lap-time model scored the result as slower.
A model built on lap times alone can't settle that argument: the next step is to score plans on finishing position.</p>
</div>
</section>

<section id="tried">
<div class="read"><h2>What I tried, and what held up</h2>
<p>Every idea was tuned on 2023 and then tested on 2024 to 2026, races it had never seen.</p></div>
<table>{idea_rows}</table>
</section>

<footer><p>Lap timing for 2018 to 2026 comes from <a href="https://github.com/TracingInsights">TracingInsights</a>, which archives
the official live-timing feed. Pirelli's compound choices are in the repository with a source for every race. This is an unofficial
project, not associated with Formula 1 or Pirelli.</p>
<p>The code, the data and the full write-up are <a href="{REPO}">on GitHub</a>. More of my projects are at <a href="https://hughod.com/">hughod.com</a>.</p></footer>
</div>"""
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>How fast do F1 tyres wear out? | Hugh O'Donnell</title>
<meta name="description" content="Tyre wear separated from fuel burn for every F1 race since 2018, forecast before each race, and tested on pit strategy.">
<link rel="canonical" href="{SITE}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&display=swap">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='12' fill='%2324282c' stroke='%23ee3b2b' stroke-width='6'/%3E%3C/svg%3E">
<style>{CSS}</style></head><body>{body}
<script>{JS.replace("__DATA__", json.dumps(data))}</script></body></html>"""
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(page)
    return str(DOCS / "index.html")
