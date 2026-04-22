"""Contract tests for /api/recent_horses.

The recorder's horse <datalist> is populated from this endpoint, so the
exact response shape and ordering are UI-visible.
"""
import time


def test_empty_when_no_recordings(client, isolated_paths):
    resp = client.get('/api/recent_horses')
    assert resp.status_code == 200
    assert resp.get_json() == {'horses': []}


def test_omits_sessions_without_horse_header(client, isolated_paths):
    client.post('/api/start', json={'location': 'arena', 'notes': 'no horse'})
    client.post('/api/stop')

    assert client.get('/api/recent_horses').get_json() == {'horses': []}


def test_returns_distinct_horses_newest_first(client, isolated_paths):
    """Dedup preserves first-seen casing and orders by most-recent session."""
    for horse in ['Spicy', 'Penny', 'Spicy']:
        client.post('/api/start', json={'location': 'arena', 'horse': horse})
        client.post('/api/stop')
        # Filenames use second-resolution timestamps; need >=1s between starts.
        time.sleep(1.05)

    horses = client.get('/api/recent_horses').get_json()['horses']
    # Most recent first: latest "Spicy", then "Penny". Second "Spicy" is deduped out.
    assert horses == ['Spicy', 'Penny']


def test_dedup_is_case_insensitive(client, isolated_paths):
    """'Spicy' and 'spicy' collapse to one entry — the first-seen casing wins."""
    client.post('/api/start', json={'location': 'arena', 'horse': 'Spicy'})
    client.post('/api/stop')
    time.sleep(1.05)
    client.post('/api/start', json={'location': 'arena', 'horse': 'spicy'})
    client.post('/api/stop')

    horses = client.get('/api/recent_horses').get_json()['horses']
    # Most-recent pass sees 'spicy' first — that's the casing we preserve.
    assert horses == ['spicy']
