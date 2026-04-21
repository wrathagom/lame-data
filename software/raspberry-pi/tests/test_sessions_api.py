"""Tests for /api/sessions — the listing view the UI depends on.

Guards the comment parser in list_sessions() (horse_recorder.py around :389).
"""


def test_sessions_empty_when_no_recordings(client, isolated_paths):
    resp = client.get('/api/sessions')
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_sessions_lists_recording_with_metadata(client, isolated_paths):
    client.post('/api/start', json={'location': 'west arena', 'notes': 'baseline run'})
    client.post('/api/stop')

    sessions = client.get('/api/sessions').get_json()
    assert len(sessions) == 1

    s = sessions[0]
    assert s['filename'].startswith('session_') and s['filename'].endswith('.csv')
    assert s['metadata']['location'] == 'west arena'
    assert s['metadata']['notes'] == 'baseline run'
    assert 'start_time' in s['metadata']
    # Known limitation: list_sessions() stops parsing at the first non-# line
    # (the CSV column header), so the `# Total Samples:` footer is never read.
    # sessions.html handles the missing key by displaying "Unknown" samples.
    # If the parser is ever fixed to read footers, update this assertion.
    assert 'samples' not in s['metadata']


def test_sessions_parses_protocol_run(client, isolated_paths):
    """The extra # Protocol / # Step Iteration headers must not confuse the
    parser — notes should still be the step instruction."""
    client.post('/api/start', json={
        'location': 'arena',
        'protocol_name': 'Standard Lameness Exam',
        'step_instruction': 'Trot in hand down and back on soft ground',
        'iteration': 1,
    })
    client.post('/api/stop')

    sessions = client.get('/api/sessions').get_json()
    assert len(sessions) == 1
    assert sessions[0]['metadata']['notes'] == 'Trot in hand down and back on soft ground'


def test_sessions_sorted_newest_first(client, isolated_paths):
    """Filename prefix contains the timestamp; list() reverse-sorts by name.
    Make sure the ordering contract holds across multiple recordings."""
    import time

    client.post('/api/start', json={'location': 'first', 'notes': ''})
    client.post('/api/stop')
    # Filenames use YYYYMMDD_HHMMSS — need at least a second between records.
    time.sleep(1.05)
    client.post('/api/start', json={'location': 'second', 'notes': ''})
    client.post('/api/stop')

    sessions = client.get('/api/sessions').get_json()
    assert len(sessions) == 2
    assert sessions[0]['metadata']['location'] == 'second'
    assert sessions[1]['metadata']['location'] == 'first'
