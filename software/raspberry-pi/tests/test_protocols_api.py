"""Contract tests for /api/protocols endpoints.

These lock down the exact JSON shapes the frontend depends on (including the
409 favorite-cap response that templates/protocols.html reads into a toast)
so a server-side refactor can't silently break the UI.
"""


def test_get_protocols_seeds_when_empty(client, isolated_paths):
    resp = client.get('/api/protocols')
    assert resp.status_code == 200

    data = resp.get_json()
    assert [p['name'] for p in data['protocols']] == ['Standard Lameness Exam']


def test_create_protocol_assigns_id_and_defaults(client, isolated_paths):
    resp = client.post('/api/protocols', json={
        'name': 'Trot Only',
        'steps': [{'instruction': 'Trot in hand'}],
    })
    assert resp.status_code == 200

    body = resp.get_json()
    assert body['name'] == 'Trot Only'
    assert body['is_favorite'] is False
    assert body['id'].startswith('proto-')
    assert len(body['steps']) == 1
    assert body['steps'][0]['id']  # server-assigned


def test_create_protocol_rejects_empty_name(client, isolated_paths):
    resp = client.post('/api/protocols', json={'name': '  ', 'steps': []})
    assert resp.status_code == 400
    assert 'error' in resp.get_json()


def test_create_protocol_persists_across_requests(client, isolated_paths):
    client.post('/api/protocols', json={'name': 'X', 'steps': []})
    second = client.get('/api/protocols').get_json()
    assert any(p['name'] == 'X' for p in second['protocols'])


def test_put_renames_and_replaces_steps(client, isolated_paths):
    created = client.post('/api/protocols', json={
        'name': 'Old',
        'steps': [{'instruction': 'old step'}],
    }).get_json()

    resp = client.put(f'/api/protocols/{created["id"]}', json={
        'name': 'New',
        'steps': [{'instruction': 'new step'}],
    })
    assert resp.status_code == 200
    assert resp.get_json()['name'] == 'New'

    reloaded = client.get('/api/protocols').get_json()
    proto = next(p for p in reloaded['protocols'] if p['id'] == created['id'])
    assert proto['name'] == 'New'
    assert [s['instruction'] for s in proto['steps']] == ['new step']


def test_put_with_only_name_preserves_steps(client, isolated_paths):
    """Partial update shouldn't wipe fields the client didn't send."""
    created = client.post('/api/protocols', json={
        'name': 'Original',
        'steps': [{'instruction': 'keep me'}],
    }).get_json()

    client.put(f'/api/protocols/{created["id"]}', json={'name': 'Renamed'})

    proto = next(p for p in client.get('/api/protocols').get_json()['protocols']
                 if p['id'] == created['id'])
    assert proto['name'] == 'Renamed'
    assert [s['instruction'] for s in proto['steps']] == ['keep me']


def test_put_rejects_empty_name(client, isolated_paths):
    created = client.post('/api/protocols', json={'name': 'A', 'steps': []}).get_json()
    resp = client.put(f'/api/protocols/{created["id"]}', json={'name': ''})
    assert resp.status_code == 400


def test_put_unknown_id_returns_404(client, isolated_paths):
    resp = client.put('/api/protocols/does-not-exist', json={'name': 'x'})
    assert resp.status_code == 404


def test_delete_removes_protocol(client, isolated_paths):
    created = client.post('/api/protocols', json={'name': 'Doomed', 'steps': []}).get_json()

    resp = client.delete(f'/api/protocols/{created["id"]}')
    assert resp.status_code == 200
    assert resp.get_json() == {'success': True}

    remaining = client.get('/api/protocols').get_json()['protocols']
    assert all(p['id'] != created['id'] for p in remaining)


def test_delete_unknown_id_returns_404(client, isolated_paths):
    resp = client.delete('/api/protocols/does-not-exist')
    assert resp.status_code == 404


def test_favorite_toggle_sets_and_unsets(client, isolated_paths):
    """Seed already has 1 favorite (Standard Lameness Exam); test toggling."""
    # Unfavorite the seed first so we start clean.
    seed_id = client.get('/api/protocols').get_json()['protocols'][0]['id']
    client.post(f'/api/protocols/{seed_id}/favorite', json={'is_favorite': False})

    created = client.post('/api/protocols', json={'name': 'F', 'steps': []}).get_json()
    resp = client.post(f'/api/protocols/{created["id"]}/favorite', json={'is_favorite': True})
    assert resp.status_code == 200
    assert resp.get_json()['is_favorite'] is True

    resp = client.post(f'/api/protocols/{created["id"]}/favorite', json={'is_favorite': False})
    assert resp.status_code == 200
    assert resp.get_json()['is_favorite'] is False


def test_favorite_cap_returns_409_with_current_favorites(client, isolated_paths):
    """Contract: UI in templates/protocols.html reads .current_favorites
    off the 409 body to render the 'Unfavorite one first' toast."""
    # Seed comes with Standard Lameness already favorited (that's 1 of 2).
    second = client.post('/api/protocols', json={'name': 'Second', 'steps': []}).get_json()
    client.post(f'/api/protocols/{second["id"]}/favorite', json={'is_favorite': True})
    # Now we have 2 favorites. The next one should 409.

    third = client.post('/api/protocols', json={'name': 'Third', 'steps': []}).get_json()
    resp = client.post(f'/api/protocols/{third["id"]}/favorite', json={'is_favorite': True})

    assert resp.status_code == 409
    body = resp.get_json()
    assert 'error' in body
    assert 'current_favorites' in body
    assert len(body['current_favorites']) == 2
    for entry in body['current_favorites']:
        assert 'id' in entry and 'name' in entry


def test_favorite_setting_same_value_is_idempotent(client, isolated_paths):
    """Re-favoriting an already-favorited protocol shouldn't trigger the cap."""
    seed_id = client.get('/api/protocols').get_json()['protocols'][0]['id']
    # Already favorite=True in seed.
    resp = client.post(f'/api/protocols/{seed_id}/favorite', json={'is_favorite': True})
    assert resp.status_code == 200


def test_favorite_unknown_id_returns_404(client, isolated_paths):
    resp = client.post('/api/protocols/missing/favorite', json={'is_favorite': True})
    assert resp.status_code == 404
