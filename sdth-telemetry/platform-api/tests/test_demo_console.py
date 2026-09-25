import json

import httpx
import pytest

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


def test_default_model_connect_requires_auth_and_warms_existing_model(client, monkeypatch):
    monkeypatch.setattr(settings, 'warm_local_model', True)
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': settings.ollama_model}]})
        assert request.url.path == '/api/generate'
        payload = json.loads(request.content)
        assert payload['prompt'] == ''
        assert payload['model'] == settings.ollama_model
        assert payload['keep_alive'] == '30m'
        return httpx.Response(200, json={'done': True})
    mock_model_server(monkeypatch, handler)
    assert client.post('/v1/demo/model/connect').status_code == 401
    response = client.post('/v1/demo/model/connect', headers=AUTH)
    assert response.status_code == 200
    assert response.json()['status'] == 'ready'
    assert response.json()['warmed'] is True
    assert calls == ['/api/tags', '/api/generate']


def test_default_model_starts_only_when_needed(monkeypatch):
    from unittest.mock import Mock
    from app import demo_api
    monkeypatch.setattr(settings, 'local_demo_worker', True)
    monkeypatch.setattr(settings, 'auto_start_local_model', True)
    monkeypatch.setattr(settings, 'warm_local_model', False)
    monkeypatch.setattr(settings, 'ollama_base_url', 'http://127.0.0.1:11434')
    monkeypatch.setattr(demo_api, '_ollama_process', None)
    statuses = iter([{'status': 'offline'}, {'status': 'ready'}])
    monkeypatch.setattr(demo_api, '_model_status', lambda: next(statuses))
    monkeypatch.setattr(demo_api.shutil, 'which', lambda name: '/usr/local/bin/ollama')
    monkeypatch.setattr(demo_api.time, 'sleep', lambda _: None)
    process = Mock()
    process.poll.return_value = None
    spawn = Mock(return_value=process)
    monkeypatch.setattr(demo_api.subprocess, 'Popen', spawn)
    assert demo_api.prepare_default_model()['status'] == 'ready'
    spawn.assert_called_once()
    assert spawn.call_args.args[0] == ['/usr/local/bin/ollama', 'serve']
    env = spawn.call_args.kwargs['env']
    assert env['OLLAMA_HOST'] == '127.0.0.1:11434'
    assert env['OLLAMA_NO_CLOUD'] == '1'
    assert env['OLLAMA_NOPRUNE'] == '1'
    monkeypatch.setattr(demo_api, '_model_status', lambda: {'status': 'ready'})
    assert demo_api.prepare_default_model()['status'] == 'ready'
    spawn.assert_called_once()


@pytest.mark.parametrize('local_demo,auto_start,url', [
    (False, True, 'http://127.0.0.1:11434'),
    (True, False, 'http://127.0.0.1:11434'),
    (True, True, 'http://host.docker.internal:11434'),
    (True, True, 'https://127.0.0.1:11434'),
])
def test_default_model_does_not_start_outside_opted_in_loopback_demo(monkeypatch, local_demo, auto_start, url):
    from unittest.mock import Mock
    from app import demo_api
    monkeypatch.setattr(settings, 'local_demo_worker', local_demo)
    monkeypatch.setattr(settings, 'auto_start_local_model', auto_start)
    monkeypatch.setattr(settings, 'ollama_base_url', url)
    monkeypatch.setattr(demo_api, '_model_status', lambda: {'status': 'offline'})
    spawn = Mock()
    monkeypatch.setattr(demo_api.subprocess, 'Popen', spawn)
    assert demo_api.prepare_default_model()['status'] == 'offline'
    spawn.assert_not_called()


def test_default_model_preload_error_is_not_reported_as_ready(client, monkeypatch):
    monkeypatch.setattr(settings, 'warm_local_model', True)
    def handler(request):
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': settings.ollama_model}]})
        return httpx.Response(500, json={'error': 'insufficient memory'})
    mock_model_server(monkeypatch, handler)
    result = client.post('/v1/demo/model/connect', headers=AUTH).json()
    assert result['status'] == 'error'
    assert result['warmed'] is False
    assert 'memory' in result['message']


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
    monkeypatch.setattr('app.demo_api._model_status', lambda *args: {'status': 'offline'})
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
    monkeypatch.setattr('app.demo_api._model_status', lambda *args: {'status': 'ready'})
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


def test_analysis_cache_returns_stored_response(client, monkeypatch):
    flight = ingest(client, monkeypatch)
    query = client.post('/v1/demo/query', headers=AUTH, json={'flight_id': flight, 'question': 'Where is the evidence?'}).json()
    evidence_id = query['evidence'][0]['id']
    monkeypatch.setattr('app.demo_api._model_status', lambda *args: {'status': 'ready'})
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {'response': json.dumps({'summary': 'Cached summary', 'hypotheses': [{'analysis': 'Possible cause', 'evidence_ids': [evidence_id], 'follow_up': 'Review records'}], 'limitations': []})}
    class Client:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs):
            calls.append(args)
            return Response()
    monkeypatch.setattr('app.demo_api.httpx.Client', Client)
    body = {'question': 'Summarize recurring patterns and evidence across stored flights.'}
    first = client.post('/v1/demo/analysis', headers=AUTH, json=body).json()
    assert first['status'] == 'generated'
    assert first['cached'] is False
    second = client.post('/v1/demo/analysis', headers=AUTH, json=body).json()
    assert second['status'] == 'generated'
    assert second['cached'] is True
    assert second['generated_at']
    assert len(calls) == 1


def test_analysis_stream_emits_deltas_then_final(client, monkeypatch):
    flight = ingest(client, monkeypatch)
    query = client.post('/v1/demo/query', headers=AUTH, json={'flight_id': flight, 'question': 'Where is the evidence?'}).json()
    evidence_id = query['evidence'][0]['id']
    monkeypatch.setattr('app.demo_api._model_status', lambda *args: {'status': 'ready'})
    full = json.dumps({'summary': 'Streamed summary', 'hypotheses': [{'analysis': 'Possible cause', 'evidence_ids': [evidence_id], 'follow_up': 'Review records'}], 'limitations': []})
    fragments = [json.dumps({'response': full[:10]}), json.dumps({'response': full[10:20]}), json.dumps({'response': full[20:], 'done': True})]
    calls = []
    class StreamResponse:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_lines(self): return iter(fragments)
    class Client:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, *args, **kwargs):
            calls.append(args)
            return StreamResponse()
    monkeypatch.setattr('app.demo_api.httpx.Client', Client)
    response = client.post('/v1/demo/analysis/stream', headers=AUTH, json={'question': 'Summarize stored flights.'})
    assert response.status_code == 200
    assert 'text/event-stream' in response.headers['content-type']
    events = [json.loads(line[5:]) for line in response.text.split('\n\n') if line.startswith('data:')]
    deltas = [e['delta'] for e in events if 'delta' in e]
    assert deltas == [full[:10], full[10:20], full[20:]]
    final = [e['final'] for e in events if 'final' in e][0]
    assert final['status'] == 'generated'
    assert final['summary'] == 'Streamed summary'
    assert len(calls) == 1


def mock_model_server(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr('app.demo_api.httpx.Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


@pytest.mark.parametrize('provider,path,body', [
    ('ollama', '/api/tags', {'models': [{'name': 'local-test'}, {'name': 'remote', 'remote_host': 'cloud'}]}),
    ('openai', '/v1/models', {'data': [{'id': 'local-test'}]}),
])
def test_model_connection_discovers_models(client, monkeypatch, provider, path, body):
    def handler(request):
        assert request.url.path == path
        assert request.headers['Authorization'] == 'Bearer test-server-token'
        return httpx.Response(200, json=body)
    mock_model_server(monkeypatch, handler)
    connection = {'provider': provider, 'base_url': 'http://127.0.0.1:1234', 'api_key': 'test-server-token'}
    assert client.post('/v1/demo/model/check', json=connection).status_code == 401
    result = client.post('/v1/demo/model/check', headers=AUTH, json=connection)
    assert result.status_code == 200
    assert result.json()['models'] == ['local-test']
    assert result.json()['status'] == 'available'
    assert 'test-server-token' not in result.text
    connection['model'] = 'not-installed'
    assert client.post('/v1/demo/model/check', headers=AUTH, json=connection).json()['status'] == 'missing'


@pytest.mark.parametrize('url', ['https://remote.example', 'http://127.0.0.1.evil.test', 'http://127.0.0.1/admin', 'http://user:pass@localhost:1234', 'http://localhost:1234?redirect=remote', 'http://169.254.169.254'])
def test_model_connection_rejects_nonlocal_or_unexpected_urls(client, url):
    result = client.post('/v1/demo/model/check', headers=AUTH, json={'base_url': url, 'provider': 'openai'})
    assert result.status_code == 422


def test_openai_stream_progress_validation_and_cache_isolation(client, monkeypatch):
    ingest(client, monkeypatch)
    generated = json.dumps({'summary': 'Local answer', 'hypotheses': [], 'limitations': []})
    calls = []
    def handler(request):
        if request.url.path == '/v1/models':
            return httpx.Response(200, json={'data': [{'id': 'judge-model'}]})
        assert request.url.path == '/v1/chat/completions'
        payload = json.loads(request.content)
        assert payload['model'] == 'judge-model'
        assert payload['messages'][0]['role'] == 'user'
        calls.append(str(request.url))
        return httpx.Response(200, text='data: ' + json.dumps({'choices': [{'delta': {'content': generated}}]}) + '\n\ndata: [DONE]\n\n')
    mock_model_server(monkeypatch, handler)
    connection = {'provider': 'openai', 'base_url': 'http://127.0.0.1:1234/v1', 'model': 'judge-model'}
    def run():
        result = client.post('/v1/demo/analysis/stream', headers=AUTH, json={'connection': connection})
        return [json.loads(line[5:]) for line in result.text.split('\n\n') if line.startswith('data:')]
    events = run()
    assert [event['stage'] for event in events if 'stage' in event] == ['connecting', 'loading', 'generating', 'validating']
    assert events[-1]['final']['status'] == 'generated'
    assert events[-1]['final']['model'] == 'judge-model'
    assert events[-1]['final']['provider'] == 'openai'
    assert run()[-1]['final']['cached'] is True
    connection['base_url'] = 'http://127.0.0.1:5678/v1'
    assert run()[-1]['final']['cached'] is False
    assert len(calls) == 2
    fresh = client.post('/v1/demo/analysis/stream', headers=AUTH, json={'connection': connection, 'fresh': True})
    assert '"cached": false' in fresh.text
    assert len(calls) == 3


@pytest.mark.parametrize('failure,status', [('unauthorized', 'unauthorized'), ('redirect', 'error'), ('offline', 'offline')])
def test_connection_failures_are_actionable_without_redirects(client, monkeypatch, failure, status):
    requests = []
    def handler(request):
        requests.append(request)
        if failure == 'offline':
            raise httpx.ConnectError('offline', request=request)
        return httpx.Response(401 if failure == 'unauthorized' else 302, headers={'Location': 'https://remote.example'})
    mock_model_server(monkeypatch, handler)
    result = client.post('/v1/demo/model/check', headers=AUTH, json={'provider': 'openai', 'base_url': 'http://localhost:1234'}).json()
    assert result['status'] == status
    assert result['message']
    assert len(requests) == 1


@pytest.mark.parametrize('raw', ['not JSON', json.dumps({'summary': 'Unverified', 'hypotheses': [{'analysis': 'Guess', 'evidence_ids': ['invented'], 'follow_up': 'Review'}]})])
def test_openai_invalid_answers_are_not_published_or_cached(client, monkeypatch, raw):
    ingest(client, monkeypatch)
    def handler(request):
        if request.url.path == '/v1/models':
            return httpx.Response(200, json={'data': [{'id': 'judge-model'}]})
        return httpx.Response(200, json={'choices': [{'message': {'content': raw}}]})
    mock_model_server(monkeypatch, handler)
    result = client.post('/v1/demo/analysis', headers=AUTH, json={'connection': {'provider': 'openai', 'base_url': 'http://localhost:1234', 'model': 'judge-model'}}).json()
    assert result['status'] == 'unavailable'
    assert result['hypotheses'] == []
    assert result['evidence']
    from app.db import db_session
    with db_session() as conn:
        assert conn.execute('SELECT COUNT(*) FROM analysis_cache').fetchone()[0] == 0


def test_ollama_custom_model_stream_thinking_and_validation(client, monkeypatch):
    ingest(client, monkeypatch)
    answer = json.dumps({'summary': 'Local Ollama answer', 'hypotheses': [], 'limitations': []})
    def handler(request):
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': 'another-model'}]})
        payload = json.loads(request.content)
        assert payload['model'] == 'another-model'
        assert payload['stream'] is True
        assert payload['format']['type'] == 'object'
        lines = [{'thinking': 'private reasoning not displayed'}, {'response': answer, 'done': True}]
        return httpx.Response(200, text='\n'.join(json.dumps(line) for line in lines))
    mock_model_server(monkeypatch, handler)
    result = client.post('/v1/demo/analysis/stream', headers=AUTH, json={'connection': {'provider': 'ollama', 'base_url': 'http://localhost:11434', 'model': 'another-model'}})
    events = [json.loads(line[5:]) for line in result.text.split('\n\n') if line.startswith('data:')]
    assert [e['stage'] for e in events if 'stage' in e] == ['connecting', 'loading', 'thinking', 'generating', 'validating']
    assert 'private reasoning' not in result.text
    assert events[-1]['final']['summary'] == 'Local Ollama answer'
    assert events[-1]['final']['model'] == 'another-model'


def test_stream_timeout_preserves_evidence(client, monkeypatch):
    ingest(client, monkeypatch)
    def handler(request):
        if request.url.path == '/v1/models':
            return httpx.Response(200, json={'data': [{'id': 'judge-model'}]})
        raise httpx.ReadTimeout('slow server', request=request)
    mock_model_server(monkeypatch, handler)
    result = client.post('/v1/demo/analysis/stream', headers=AUTH, json={'connection': {'provider': 'openai', 'base_url': 'http://localhost:1234', 'model': 'judge-model'}})
    events = [json.loads(line[5:]) for line in result.text.split('\n\n') if line.startswith('data:')]
    assert events[-1]['final']['status'] == 'unavailable'
    assert events[-1]['final']['evidence']
    assert 'timed out' in events[-1]['final']['summary']
