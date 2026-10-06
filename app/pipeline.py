"""Deterministic ingestion and conservative entry-to-attempt attribution."""
import csv
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/raw/hackathon_nwhl.csv'
DB = ROOT / 'data/events.sqlite'
POSSESSION = {'Play', 'Puck Recovery', 'Takeaway', 'Shot', 'Goal', 'Zone Entry', 'Dump In/Out'}

def normalize(path=SOURCE):
    events, rejected = [], []
    with open(path, newline='', encoding='utf-8-sig') as f:
        for index, raw in enumerate(csv.DictReader(f), 2):
            r = {k: v.strip() for k, v in raw.items()}
            try:
                period = int(r['Period'])
                minutes, seconds = map(int, r['Clock'].split(':'))
                remaining = minutes * 60 + seconds
                if period < 1 or not 0 <= seconds < 60 or not 0 <= remaining <= 1200:
                    raise ValueError('invalid period or clock')
                if r['Team'] not in (r['Home Team'], r['Away Team']):
                    raise ValueError('event team is not a participant')
                x, y = float(r['X Coordinate']), float(r['Y Coordinate'])
                if not (0 <= x <= 200 and 0 <= y <= 85):
                    raise ValueError('coordinates outside rink')
                home, away = int(r['Home Team Skaters']), int(r['Away Team Skaters'])
                if not (3 <= home <= 6 and 3 <= away <= 6):
                    raise ValueError('invalid skater count')
                own, opponent = (home, away) if r['Team'] == r['Home Team'] else (away, home)
                events.append(dict(id=index, game=' | '.join([r['game_date'], r['Home Team'], r['Away Team']]),
                    period=period, remaining=remaining, clock=r['Clock'], team=r['Team'], player=r['Player'],
                    event=r['Event'], detail=r['Detail 1'], outcome=r['Detail 2'], x=x, y=y,
                    strength='5v5' if own == opponent == 5 else 'Advantage' if own > opponent else 'Disadvantage' if own < opponent else 'Other even',
                    own_skaters=own, opponent_skaters=opponent))
            except (ValueError, KeyError) as exc:
                rejected.append({'row': index, 'reason': str(exc)})
    # Source row order breaks ties: clocks alone cannot order same-second events.
    events.sort(key=lambda e: (e['game'], e['period'], -e['remaining'], e['id']))
    return events, rejected

def sequences(events, window=20):
    groups = {}
    for e in events:
        groups.setdefault((e['game'], e['period']), []).append(e)
    entries = []
    for group in groups.values():
        for i, entry in enumerate(group):
            if entry['event'] != 'Zone Entry' or entry['detail'] not in ('Carried', 'Dumped', 'Played'):
                continue
            trace, shots = [], []
            boundary = 'Period end'
            for e in group[i + 1:]:
                delta = entry['remaining'] - e['remaining']
                if delta > window:
                    boundary = 'Time window'
                    break
                reason = None
                if e['event'] in ('Faceoff Win', 'Penalty Taken'):
                    reason = 'Stoppage'
                elif e['event'] == 'Zone Entry':
                    reason = 'New entry'
                elif e['team'] != entry['team'] and e['event'] in POSSESSION:
                    reason = 'Opponent possession evidence'
                elif (e['team'] == entry['team'] and e['event'] in POSSESSION and e['x'] < 125
                      and not (entry['detail'] == 'Dumped' and e['event'] == 'Dump In/Out' and delta == 0)):
                    reason = 'Outside offensive zone'
                if reason:
                    boundary = reason
                    trace.append(dict(e, seconds=delta, boundary=True))
                    break
                trace.append(dict(e, seconds=delta, boundary=False))
                if e['team'] == entry['team'] and e['event'] in ('Shot', 'Goal'):
                    shots.append(dict(e, seconds=delta))
                    if e['event'] == 'Goal':
                        boundary = 'Goal'
                        break
            entries.append(dict(entry, shots=shots, trace=trace, boundary=boundary))
    return entries

def build():
    events, rejected = normalize()
    DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB) as conn:
        conn.execute('DROP TABLE IF EXISTS events')
        conn.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, game TEXT, period INTEGER, remaining INTEGER, payload TEXT)')
        conn.executemany('INSERT INTO events VALUES (?,?,?,?,?)', [(e['id'], e['game'], e['period'], e['remaining'], json.dumps(e)) for e in events])
        conn.execute('CREATE INDEX event_order ON events(game, period, remaining DESC, id)')
    report = dict(source=SOURCE.name, sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(), accepted=len(events), rejected=rejected,
                  games=len({e['game'] for e in events}), entries=sum(e['event']=='Zone Entry' for e in events))
    (ROOT/'data/quality.json').write_text(json.dumps(report, indent=2))
    return report

def read_events():
    with sqlite3.connect(DB) as conn:
        return [json.loads(row[0]) for row in conn.execute('SELECT payload FROM events ORDER BY game, period, remaining DESC, id')]

if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
