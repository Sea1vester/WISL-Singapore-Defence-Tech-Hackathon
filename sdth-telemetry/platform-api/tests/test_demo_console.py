import json

from app.config import settings
from app.demo_api import _is_local_model
from tests.conftest import AUTH
from app.worker import process_raw_upload, process_job
from pathlib import Path

FIXTURE = Path(__file__).parents[2] / 'fixtures/demo/controller_mission_alpha.csv'


def ingest(client, monkeypatch):
    monkeypatch.setattr(settings, 'ingest_model_enrichment', False)
    jobs = []
    monkeypatch.setattr('app.worker.enqueue_translation_job', jobs.append)
    response = client.post('/v1/logs/upload', headers=AUTH, files={'file': ('demo.csv', FIXTURE.read_bytes())})
    upload_id = response.json()['upload_id']
    process_raw_upload(upload_id)
    process_job(jobs[0])
    status = client.get(f'/v1/uploads/{upload_id}', headers=AUTH).json()
    assert status['status'] == 'ready'
    return status['flight_id']


def test_demo_requires_auth_and_empty_analysis_is_honest(client):
    assert client.get('/v1/demo/status').status_code == 401
    result = client.post('/v1/demo/analysis', headers=AUTH, json={}).json()
    assert result['status'] == 'empty'
    assert result['coverage']['total_flights'] == 0
    assert result['hypotheses'] == []


def test_evidence_query_follows_actual_ingested_records(client, monkeypatch):
    flight = ingest(client, monkeypatch)
    result = client.post('/v1/demo/query', headers=AUTH, json={'flight_id': flight, 'question': 'Where is the evidence?'}).json()
    assert result['method'].startswith('deterministic')
    assert result['evidence']
    assert all(e['flight_id'] == flight for e in result['evidence'])
    assert any('operator_warning' == e['incident_type'] for e in result['evidence'])
    related = client.post('/v1/demo/query', headers=AUTH, json={'flight_id': flight, 'question': 'Which other flights show the same warning?'}).json()
    assert related['related_flights'] == []
    assert 'No other' in related['answer']


def test_offline_analysis_preserves_evidence(client, monkeypatch):
    flight = ingest(client, monkeypatch)
    monkeypatch.setattr('app.demo_api._model_status', lambda: {'status': 'offline'})
    result = client.post('/v1/demo/analysis', headers=AUTH, json={'flight_id': flight}).json()
    assert result['status'] == 'unavailable'
    assert result['evidence']
    assert result['coverage']['raw_samples_in_prompt'] is False


def test_nonlocal_model_rejected(monkeypatch):
    monkeypatch.setattr(settings, 'ollama_base_url', 'https://third-party.example')
    assert not _is_local_model()
    monkeypatch.setattr(settings, 'ollama_base_url', 'http://127.0.0.1:11434')
    monkeypatch.setattr(settings, 'ollama_model', 'test:cloud')
    assert not _is_local_model()
    monkeypatch.setattr(settings, 'ollama_model', 'deepseek-r1:7b')
    assert _is_local_model()


def test_unknown_model_evidence_is_not_published(client, monkeypatch):
    flight = ingest(client, monkeypatch)
    monkeypatch.setattr('app.demo_api._model_status', lambda: {'status': 'ready'})
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {'response': json.dumps({'summary': 'Unverified', 'hypotheses': [{'analysis': 'Cause', 'evidence_ids': ['fabricated-id'], 'follow_up': 'Review'}], 'limitations': []})}
    class Client:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr('app.demo_api.httpx.Client', Client)
    result = client.post('/v1/demo/analysis', headers=AUTH, json={'flight_id': flight}).json()
    assert result['status'] == 'unavailable'
    assert result['hypotheses'] == []
    assert result['reason'] == 'ValueError'


def test_worker_recovery_resumes_interrupted_normalization(client, monkeypatch):
    from app.db import db_session
    from app.local_worker import recover
    queued = []
    monkeypatch.setattr('app.worker.enqueue_translation_job', queued.append)
    response = client.post('/v1/logs/upload', headers=AUTH, files={'file': ('demo.csv', FIXTURE.read_bytes())})
    upload_id = response.json()['upload_id']
    process_raw_upload(upload_id)
    with db_session() as conn:
        conn.execute("UPDATE translation_jobs SET status='done' WHERE id=?", (queued[0],))
        conn.execute("UPDATE raw_uploads SET status='detecting' WHERE id=?", (upload_id,))
    resumed = []
    monkeypatch.setattr('app.local_worker.submit', lambda kind, job_id: resumed.append((kind, job_id)))
    recover()
    assert ('translation', queued[0]) in resumed


def test_different_warning_texts_are_not_reported_as_same_warning(client, monkeypatch):
    first = ingest(client, monkeypatch)
    jobs = []
    monkeypatch.setattr('app.worker.enqueue_translation_job', jobs.append)
    other = FIXTURE.read_bytes().replace(b'GPS signal weak', b'Compass error')
    response = client.post('/v1/logs/upload', headers=AUTH, files={'file': ('compass.csv', other)})
    process_raw_upload(response.json()['upload_id'])
    process_job(jobs[0])
    result = client.post('/v1/demo/query', headers=AUTH, json={'flight_id': first, 'question': 'Which other flights show the same warning?'}).json()
    assert result['related_flights'] == []
    assert 'exact warning text' in result['answer']
