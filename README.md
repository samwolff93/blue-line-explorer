# Blue Line — Zone Entry Explorer

A coaching interface for one question: **which offensive-zone entries turn into shot attempts?** Built for the Calgary Flames developer interview exercise. Python owns ingestion, validation, storage, attribution, filtering, and statistics. A small HTML/CSS/JavaScript frontend presents comparisons, shot locations, and inspectable sequences.

## Run locally

Python 3.9+ (Docker uses 3.12).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.pipeline
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. API documentation: `/docs`. Tests: `python -m pytest -q`.

## Data engineering

Source: [Stathletes / Big Data Cup](https://github.com/bigdatacup/Big-Data-Cup-2021), `hackathon_nwhl.csv`. The bundled snapshot contains 26,882 events, 15 games, six teams, and 1,944 Zone Entry records. The default 5-on-5 sample contains 1,581 entries. We deliberately use one competition rather than pooling NCAA, NWHL, and international contexts.

`app/pipeline.py` trims text and validates clock syntax and bounds, periods, participating teams, rink coordinates, and skater counts. Rejected rows are logged by source row and reason; no source rows are silently repaired. All rows in this snapshot pass validation. The pipeline writes normalized JSON event records into SQLite with an ordering index and emits `data/quality.json`, including a SHA-256 fingerprint. Original CSV rows stay unchanged. Events are ordered by game, period, descending time remaining, and original row number for same-second ties. Duplicate-looking rows are retained because distinct actions can share a clock.

Rebuild explicitly after changing the source (`python -m app.pipeline`) and restart the server to clear derived caches. The bundled source is fixed for this exercise. Importing an incompatible schema requires adapting and testing the ingestion contract.

## Metric definitions

- **Entry:** a Zone Entry event labeled Carried, Dumped, or Played. Played is displayed as Pass.
- **Productive entry:** at least one subsequent same-team Shot or Goal before a boundary and within 10, 20, or 30 seconds, inclusive. Goals are separate source events and are counted as attempts.
- **Boundaries:** a new entry by either team; a faceoff or penalty; a goal; a period end; opponent possession evidence (Play, Recovery, Takeaway, Shot, Goal, Entry, or Dump); or a same-team possession event with x < 125, indicating the puck is outside the offensive zone. A same-second Dump In/Out accompanying a dumped entry is part of entry release and does not itself imply a zone exit.
- **Incomplete Play:** does not establish opponent possession by itself.
- **Dump recoveries:** remain eligible until opponent possession evidence, so a same-team loose-puck recovery can lead to an attributed shot.
- **Situation:** skater counts at entry, with 5v5 as the default. This is not goalie-status information and does not enforce unchanged manpower throughout the sequence.
- **Rate denominator:** all filtered entries, including entries that end early. Attempts can exceed productive entries because sequences may contain multiple shots.
- **Time to attempt:** median delay across all attributed attempts, not solely the first shot per entry.
- **Uncertainty:** 95% Wilson binomial intervals; zero-entry groups show no rate. Samples below 30 are flagged. These intervals do not model within-game clustering.

The rink uses event-team coordinates (0–200 by 0–85), with offensive events toward the right. This app does not fit an expected-goals model. Shot location is a descriptive view.

## Findings and coaching use

Default setting: all teams, 5-on-5, 20-second window.

| Entry | Entries | Entries with attempt | Rate | 95% Wilson interval |
|---|---:|---:|---:|---:|
| Carry | 978 | 512 | 52.4% | 49.2–55.5% |
| Dump | 521 | 29 | 5.6% | 3.9–7.9% |
| Pass | 82 | 46 | 56.1% | 45.3–66.3% |

At 10 seconds, carry/dump/pass rates are 51.1% / 4.4% / 52.4%; at 30 seconds, 52.8% / 5.6% / 56.1%. The ranking persists across these windows. Most dumped sequences end on opponent possession evidence. That is a reason to inspect recoveries and forecheck execution, not a blanket instruction to stop dumping the puck. Carry and pass intervals overlap, and pass entries have a much smaller sample.

A coach can filter their team, compare entry modes, inspect where subsequent shots occur, and open individual entries to see the boundary events behind each result. Export includes the current table search and filters, source entry IDs, attribution boundary, shot counts, and window length.

These are associations in 15 NWHL games, not evidence of NHL effectiveness or a causal effect of choosing an entry type. Opponent pressure, personnel, score state, and tactical intent may explain selection and outcomes. Event-derived possession is imperfect: this dataset does not continuously track possession or whistles. Same-second order follows the provider's row order. Entries near period end have less opportunity. Future work should use game-clustered uncertainty, explicit possession validation, score-state adjustment, and sensitivity to boundary definitions.

## Architecture and tradeoffs

CSV → validated events → SQLite → conservative derived sequences → FastAPI → browser.

The dataset fits comfortably in memory. Derived sequences are cached for the three allowed windows; filters and statistics remain server-side. A custom frontend makes the coaching flow compact without requiring a frontend build tool. The pipeline uses Python's standard CSV and SQLite libraries; pandas was unnecessary for this fixed, small schema. No machine-learning model is introduced where sample size and labels do not justify one.

## Deployment

Docker:

```bash
docker build -t blue-line .
docker run --rm -p 8000:8000 blue-line
```

A Render Blueprint is included in `render.yaml`. Push this repository to GitHub, create a Render Blueprint from it, and verify `/health` and the dashboard after deployment. The Docker build generates SQLite from the bundled CSV; no external database or secrets are needed. Free hosting may sleep between visits. Docker/Render deployment is configured but has not been executed in this workspace.

Before submitting: confirm the public GitHub repository and live deployment URLs work in a signed-out browser; verify filters and a sequence; add both URLs to the submission. This workspace currently has no Git remote or hosting account configured.

## Attribution and terms

Data provided by Stathletes for the Ottawa Hockey Analytics Conference Big Data Cup. See `data/raw/legal.md`: research may be publicly shared provided it is not used for profit. This project is a noncommercial interview/research demonstration. Source repository: https://github.com/bigdatacup/Big-Data-Cup-2021.
