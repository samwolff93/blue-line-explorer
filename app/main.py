from contextlib import asynccontextmanager
from functools import lru_cache
import json
import math
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.pipeline import ROOT, DB, build, read_events, sequences

@asynccontextmanager
async def lifespan(app):
    if not DB.exists():
        build()
    yield

app = FastAPI(title='Blue Line — Zone Entry Explorer', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=ROOT/'app/static'), name='static')

@lru_cache(maxsize=3)
def entries(window):
    if window not in (10,20,30):
        from fastapi import HTTPException
        raise HTTPException(422, 'Window must be 10, 20, or 30 seconds')
    return sequences(read_events(), window)

def wilson(successes, n):
    if not n:
        return [0, 0]
    p, z = successes/n, 1.96
    center = (p+z*z/(2*n))/(1+z*z/n)
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return [round(100*(center-half), 1), round(100*(center+half), 1)]

@app.get('/')
def home():
    return FileResponse(ROOT/'app/static/index.html')

@app.get('/health')
def health():
    return {'status': 'ok'}

@app.get('/api/options')
def options():
    es = entries(20)
    return {key: sorted({e[key] for e in es}) for key in ('team', 'player', 'game', 'strength')}

@app.get('/api/explore')
def explore(window: int = Query(20, ge=10, le=30), team: str = '', player: str = '', game: str = '', strength: str = '5v5', entry_type: str = ''):
    es = [e for e in entries(window) if all(not value or e[key] == value for key,value in [('team',team),('player',player),('game',game),('strength',strength),('detail',entry_type)])]
    comparisons = []
    for kind in ('Carried','Dumped','Played'):
        group = [e for e in es if e['detail']==kind]
        n = len(group)
        success = sum(bool(e['shots']) for e in group)
        comparisons.append(dict(type=kind, entries=n, productive=success, rate=round(success/n*100,1) if n else None,
            interval=wilson(success,n), attempts=sum(len(e['shots']) for e in group)))
    shots = [dict(s, entry_id=e['id'], entry_type=e['detail']) for e in es for s in e['shots']]
    times = sorted(s['seconds'] for s in shots)
    median = (times[(len(times)-1)//2]+times[len(times)//2])/2 if times else None
    return dict(total=len(es), productive=sum(bool(e['shots']) for e in es), attempts=len(shots), median=median,
        comparisons=comparisons, shots=shots, entries=[{k:v for k,v in e.items() if k!='trace'} for e in es],
        boundaries={b:sum(e['boundary']==b for e in es) for b in sorted({e['boundary'] for e in es})})

@app.get('/api/entry/{entry_id}')
def entry(entry_id: int, window: int = Query(20, ge=10, le=30)):
    from fastapi import HTTPException
    for e in entries(window):
        if e['id'] == entry_id:
            return e
    raise HTTPException(404, 'Entry not found')

@app.get('/api/quality')
def quality():
    return json.loads((ROOT/'data/quality.json').read_text())
