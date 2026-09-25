import pytest

from app.db import db_session, run_migrations
from tests.conftest import AUTH


def folder(client, name, parent_id=None):
    response = client.post('/v1/library/folders', headers=AUTH, json={'name': name, 'parent_id': parent_id})
    assert response.status_code == 201, response.text
    return response.json()


def test_library_authentication(client):
    assert client.get('/v1/library').status_code == 401
    assert client.post('/v1/library/folders', json={'name': 'Private'}).status_code == 401
    assert client.put('/v1/library/folders/missing', json={'name': 'Private'}).status_code == 401
    assert client.put('/v1/library/flights/missing/folder', json={'folder_id': None}).status_code == 401


def test_nested_folders_and_flight_moves_survive_migrations(client):
    with db_session() as conn:
        conn.execute("INSERT INTO flights (id, source, started_at) VALUES ('mission-a', 'dji-csv', '2026-03-18T09:00:00Z')")
    parent = folder(client, 'Singapore')
    child = folder(client, 'Hillview', parent['id'])
    response = client.put('/v1/library/flights/mission-a/folder', headers=AUTH, json={'folder_id': child['id']})
    assert response.status_code == 200
    run_migrations()
    library = client.get('/v1/library', headers=AUTH).json()
    assert len(library['folders']) == 2
    assert library['flight_folders'] == {'mission-a': child['id']}
    assert client.put('/v1/library/folders/' + child['id'], headers=AUTH, json={'name': 'Inspections', 'parent_id': None}).status_code == 200
    library = client.get('/v1/library', headers=AUTH).json()
    renamed = next(item for item in library['folders'] if item['id'] == child['id'])
    assert renamed['name'] == 'Inspections'
    assert renamed['parent_id'] is None
    assert library['flight_folders']['mission-a'] == child['id']
    assert client.put('/v1/library/flights/mission-a/folder', headers=AUTH, json={'folder_id': None}).status_code == 200
    assert client.get('/v1/library', headers=AUTH).json()['flight_folders'] == {}
    with db_session() as conn:
        assert conn.execute("SELECT source FROM flights WHERE id='mission-a'").fetchone()['source'] == 'dji-csv'


@pytest.mark.parametrize('name', ['', '  ', '.', '..', 'a/b', 'a\\b', 'bad\x00name', 'a' * 81])
def test_rejects_invalid_folder_names(client, name):
    assert client.post('/v1/library/folders', headers=AUTH, json={'name': name}).status_code == 422


def test_sibling_names_are_unique_but_other_parents_can_reuse_them(client):
    parent = folder(client, '  Singapore  ')
    assert parent['name'] == 'Singapore'
    assert client.post('/v1/library/folders', headers=AUTH, json={'name': 'SINGAPORE'}).status_code == 409
    nested = folder(client, 'Singapore', parent['id'])
    assert client.put('/v1/library/folders/' + nested['id'], headers=AUTH, json={'name': 'singapore', 'parent_id': None}).status_code == 409
    assert next(item for item in client.get('/v1/library', headers=AUTH).json()['folders'] if item['id'] == nested['id'])['parent_id'] == parent['id']


def test_moves_reject_cycles_and_unknown_targets(client):
    a = folder(client, 'A')
    b = folder(client, 'B', a['id'])
    for target in [a['id'], b['id']]:
        assert client.put('/v1/library/folders/' + a['id'], headers=AUTH, json={'name': 'A', 'parent_id': target}).status_code == 409
    assert client.post('/v1/library/folders', headers=AUTH, json={'name': 'Lost', 'parent_id': 'missing'}).status_code == 404
    assert client.put('/v1/library/folders/missing', headers=AUTH, json={'name': 'Lost'}).status_code == 404
    assert client.put('/v1/library/flights/missing/folder', headers=AUTH, json={'folder_id': a['id']}).status_code == 404
    with db_session() as conn:
        conn.execute("INSERT INTO flights (id, source, started_at) VALUES ('mission-a', 'dji-csv', '2026-03-18T09:00:00Z')")
    assert client.put('/v1/library/flights/mission-a/folder', headers=AUTH, json={'folder_id': 'missing'}).status_code == 404


def test_folder_depth_is_bounded_for_creation_and_subtree_moves(client):
    parent = None
    for depth in range(16):
        parent = folder(client, str(depth), parent)['id']
    assert client.post('/v1/library/folders', headers=AUTH, json={'name': 'Too deep', 'parent_id': parent}).status_code == 409
    other = folder(client, 'Other')
    folder(client, 'Nested', other['id'])
    assert client.put('/v1/library/folders/' + other['id'], headers=AUTH, json={'name': 'Other', 'parent_id': parent}).status_code == 409
