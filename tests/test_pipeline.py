from app.pipeline import sequences, normalize
from app.main import app
from fastapi.testclient import TestClient

def event(id, kind, team='A', remaining=1100, x=140, detail=''):
    return dict(id=id,event=kind,team=team,remaining=remaining,x=x,y=40,detail=detail,game='G',period=1)

def test_dump_recovery_and_goal_are_attributed():
    rows=[event(1,'Zone Entry',detail='Dumped'),event(2,'Dump In/Out',remaining=1100,x=100),event(3,'Puck Recovery',remaining=1098),event(4,'Goal',remaining=1095)]
    # Same-second dump release is part of entry, not an inferred zone exit.
    assert len(sequences(rows)[0]['shots'])==1
    assert sequences(rows)[0]['boundary']=='Goal'

def test_opponent_possession_stops_attribution():
    rows=[event(1,'Zone Entry',detail='Carried'),event(2,'Takeaway',team='B',remaining=1098),event(3,'Shot',remaining=1095)]
    assert sequences(rows)[0]['shots']==[]

def test_same_second_order_and_period_boundary():
    rows=[event(1,'Shot'),event(2,'Zone Entry',detail='Played'),event(3,'Shot')]
    assert [s['id'] for s in sequences(rows)[0]['shots']]==[3]
    rows[-1]['period']=2
    assert not sequences(rows)[0]['shots']

def test_window_new_entry_and_incomplete_pass():
    rows=[event(1,'Zone Entry',detail='Carried'),event(2,'Incomplete Play',team='B',remaining=1099),event(3,'Shot',remaining=1090),event(4,'Shot',remaining=1089),event(5,'Zone Entry',remaining=1088,detail='Played'),event(6,'Shot',remaining=1087)]
    assert len(sequences(rows,10)[0]['shots'])==1
    assert len(sequences(rows,20)[0]['shots'])==2
    assert len(sequences(rows,20)[1]['shots'])==1

def test_source_and_api():
    events,rejected=normalize()
    assert len(events)==26882 and not rejected
    with TestClient(app) as client:
        assert client.get('/').status_code==200
        response=client.get('/api/explore?strength=&window=20').json()
        assert response['total']==1944
        assert sum(c['entries'] for c in response['comparisons'])==1944
        assert response['attempts']==len(response['shots'])
        assert client.get('/api/explore?window=99').status_code==422
        assert client.get('/api/explore?team=missing').json()['total']==0
        assert client.get('/api/entry/0').status_code==404

def test_zone_exit_and_stoppage_prevent_later_shots():
    for boundary in [event(2,'Play',remaining=1099,x=124),event(2,'Penalty Taken',remaining=1099),event(2,'Faceoff Win',remaining=1099)]:
        rows=[event(1,'Zone Entry',detail='Carried'),boundary,event(3,'Shot',remaining=1098)]
        assert not sequences(rows)[0]['shots']

def test_invalid_source_row_is_audited(tmp_path):
    import csv
    from app.pipeline import SOURCE
    with SOURCE.open() as f:
        reader=csv.DictReader(f)
        row=next(reader)
        fields=reader.fieldnames
    row['Clock']='19:75'
    path=tmp_path/'invalid.csv'
    with path.open('w') as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)
    events,rejected=normalize(path)
    assert not events
    assert rejected==[{'row':2,'reason':'invalid period or clock'}]
