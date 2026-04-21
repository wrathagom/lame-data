"""Tests for /api/start and /api/stop including protocol metadata emission.

The CSV header lines are a de facto schema — the desktop viewer and any cloud
ingest parser read them. These tests lock the exact prefix strings so a
well-meaning refactor can't drift the format.
"""
import os


def _read_csv_header(data_dir, expected_count=1):
    """Return the list of non-blank, comment-or-column-header lines from the
    single CSV created in data_dir."""
    files = [f for f in os.listdir(str(data_dir)) if f.endswith('.csv')]
    assert len(files) == expected_count, f"expected {expected_count} CSV, got {files}"
    path = os.path.join(str(data_dir), files[0])
    with open(path) as f:
        return [line.rstrip('\n') for line in f if line.strip()]


def test_start_without_protocol_emits_baseline_headers(client, isolated_paths):
    """Manual recording path: existing header shape is unchanged."""
    resp = client.post('/api/start', json={'location': 'arena', 'notes': 'manual run'})
    assert resp.status_code == 200 and resp.get_json()['success']
    client.post('/api/stop')

    lines = _read_csv_header(isolated_paths['data_dir'])

    # Baseline headers that pre-existed the protocols feature.
    assert any(l.startswith('# Location: arena') for l in lines)
    assert any(l.startswith('# Notes: manual run') for l in lines)
    assert any(l.startswith('# Start Time:') for l in lines)
    assert any(l.startswith('# Device Config:') for l in lines)
    # Protocol headers must NOT appear on a manual recording.
    assert not any(l.startswith('# Protocol:') for l in lines)
    assert not any(l.startswith('# Step Iteration:') for l in lines)


def test_start_with_protocol_emits_protocol_headers(client, isolated_paths):
    client.post('/api/start', json={
        'location': 'test-arena',
        'protocol_name': 'Standard Lameness Exam',
        'step_instruction': 'Walk in hand down and back on soft ground',
        'iteration': 2,
    })
    client.post('/api/stop')

    lines = _read_csv_header(isolated_paths['data_dir'])

    assert any(l == '# Protocol: Standard Lameness Exam' for l in lines)
    assert any(l == '# Step Iteration: 2' for l in lines)
    # step_instruction overrides notes.
    assert any(l == '# Notes: Walk in hand down and back on soft ground' for l in lines)


def test_step_instruction_overrides_notes_field(client, isolated_paths):
    """If both are sent (shouldn't happen but defensive), step wins."""
    client.post('/api/start', json={
        'location': 'x',
        'notes': 'freeform user notes',
        'protocol_name': 'P',
        'step_instruction': 'trot',
    })
    client.post('/api/stop')

    lines = _read_csv_header(isolated_paths['data_dir'])
    assert any(l == '# Notes: trot' for l in lines)
    assert not any('freeform user notes' in l for l in lines)


def test_iteration_defaults_to_1(client, isolated_paths):
    client.post('/api/start', json={
        'location': 'x',
        'protocol_name': 'P',
        'step_instruction': 'walk',
    })
    client.post('/api/stop')

    lines = _read_csv_header(isolated_paths['data_dir'])
    assert any(l == '# Step Iteration: 1' for l in lines)


def test_iteration_coerces_bad_values(client, isolated_paths):
    """Client sending iteration='foo' shouldn't crash the server."""
    client.post('/api/start', json={
        'location': 'x',
        'protocol_name': 'P',
        'step_instruction': 'walk',
        'iteration': 'not-a-number',
    })
    client.post('/api/stop')

    lines = _read_csv_header(isolated_paths['data_dir'])
    assert any(l == '# Step Iteration: 1' for l in lines)


def test_start_while_recording_returns_400(client, isolated_paths):
    client.post('/api/start', json={'location': 'x'})
    resp = client.post('/api/start', json={'location': 'y'})
    assert resp.status_code == 400
    client.post('/api/stop')


def test_stop_when_not_recording_returns_400(client, isolated_paths):
    resp = client.post('/api/stop')
    assert resp.status_code == 400


def test_stop_writes_footer_lines(client, isolated_paths):
    """End Time / Total Samples / Sync Offsets footers must be present —
    the sessions list parser relies on Total Samples."""
    client.post('/api/start', json={'location': 'x', 'notes': 'n'})
    client.post('/api/stop')

    lines = _read_csv_header(isolated_paths['data_dir'])
    assert any(l.startswith('# End Time:') for l in lines)
    assert any(l.startswith('# Total Samples:') for l in lines)
    assert any(l.startswith('# Sync Offsets:') for l in lines)


def test_csv_column_header_present(client, isolated_paths):
    """The single non-comment line before data must match the expected columns,
    or every downstream parser breaks."""
    client.post('/api/start', json={'location': 'x', 'notes': 'n'})
    client.post('/api/stop')

    lines = _read_csv_header(isolated_paths['data_dir'])
    non_comment = [l for l in lines if not l.startswith('#')]
    assert non_comment == [
        'timestamp,device_id,millis_time,accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z'
    ]
