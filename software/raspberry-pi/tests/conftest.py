"""Shared fixtures for horse_recorder tests.

Isolation rules:
  - Set UDP_PORT=0 / WEB_PORT=0 / DATA_DIR=<tmp> BEFORE importing horse_recorder,
    so the module-level UDP listener binds an ephemeral port and os.makedirs
    doesn't touch the real data directory.
  - Each test gets a fresh tmp_path for DATA_DIR, PROTOCOLS_FILE, and
    DEVICE_CONFIG_FILE via monkeypatching the module-level constants
    (Python looks up module globals at call time, so this works for the
    endpoints that reference them).
  - Recording state is module-level; the `client` fixture resets it between
    tests so a forgotten stop_recording() in one test can't leak into another.
"""
import os
import sys
import json
import tempfile
from pathlib import Path

import pytest

# Locate the raspberry-pi package root (one directory up from tests/).
PI_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PI_ROOT))

# Env overrides must be in place before horse_recorder is imported.
# UDP_PORT=0 asks the OS for any free port so we don't clash with a running
# instance or another test process. DATA_DIR points at a session-scoped tmp
# so the import-time os.makedirs() call is harmless.
_SESSION_TMP = Path(tempfile.mkdtemp(prefix='lame-data-tests-'))
os.environ['UDP_PORT'] = '0'
os.environ['WEB_PORT'] = '0'
os.environ['DATA_DIR'] = str(_SESSION_TMP / 'data')
# Make sure cloud upload paths stay inert during tests.
os.environ.pop('CLOUD_URL', None)
os.environ.pop('CLOUD_API_KEY', None)

import horse_recorder  # noqa: E402  (intentional import-after-env-setup)


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """Point every on-disk file the app touches at a per-test tmp_path."""
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    protocols_file = tmp_path / 'protocols.json'
    device_config_file = tmp_path / 'device_config.json'

    monkeypatch.setattr(horse_recorder, 'DATA_DIR', str(data_dir))
    monkeypatch.setattr(horse_recorder, 'PROTOCOLS_FILE', protocols_file)
    monkeypatch.setattr(horse_recorder, 'DEVICE_CONFIG_FILE', device_config_file)

    return {
        'data_dir': data_dir,
        'protocols_file': protocols_file,
        'device_config_file': device_config_file,
        'tmp_path': tmp_path,
    }


@pytest.fixture
def reset_recording_state():
    """Ensure recording_state is clean before the test and after teardown.

    If a test crashes mid-recording, leaving is_recording=True would poison
    every subsequent test. This fixture guarantees a clean slate both ways.
    """
    def _reset():
        recorder = horse_recorder.recording_state.get('recorder')
        if recorder is not None:
            try:
                recorder.stop()
            except Exception:
                pass
        horse_recorder.recording_state.update({
            'is_recording': False,
            'recorder': None,
            'session_start': None,
            'location': '',
            'notes': '',
            'samples_received': 0,
            'device_status': {},
            'sync_offsets': {},
        })

    _reset()
    yield
    _reset()


@pytest.fixture
def client(isolated_paths, reset_recording_state):
    """Flask test client with isolated filesystem and clean recording state."""
    horse_recorder.app.config['TESTING'] = True
    with horse_recorder.app.test_client() as c:
        yield c


@pytest.fixture
def seeded_protocols(isolated_paths):
    """Write the default seed to the per-test protocols file and return it."""
    horse_recorder.save_protocols(horse_recorder.DEFAULT_PROTOCOLS)
    with open(isolated_paths['protocols_file']) as f:
        return json.load(f)
