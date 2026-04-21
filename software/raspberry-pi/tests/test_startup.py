"""Smoke tests: module imports, critical routes are registered.

These tests are the first line of defense — they catch syntax errors and
accidental route removals that would otherwise make it to the Pi.
"""
import horse_recorder


def test_module_imports():
    assert hasattr(horse_recorder, 'app')
    assert hasattr(horse_recorder, 'recording_state')


def _registered_rules():
    return {rule.rule for rule in horse_recorder.app.url_map.iter_rules()}


# Every route the frontend templates and the Pi service rely on.
EXPECTED_ROUTES = {
    # Pages
    '/',
    '/sessions',
    '/protocols',
    '/settings',
    '/config',
    '/view/<filename>',
    # Status & device config
    '/api/status',
    '/api/device_config',
    # Protocol CRUD
    '/api/protocols',
    '/api/protocols/<protocol_id>',
    '/api/protocols/<protocol_id>/favorite',
    # Recording lifecycle
    '/api/start',
    '/api/stop',
    '/api/sync',
    '/api/sessions',
    '/api/session_data/<filename>',
    # Management
    '/api/download/<filename>',
    '/api/download_batch',
}


def test_expected_routes_registered():
    rules = _registered_rules()
    missing = EXPECTED_ROUTES - rules
    assert not missing, f"missing routes: {missing}"


def test_protocol_routes_have_expected_methods():
    """Regression guard: if someone accidentally drops a method off an
    existing route, this catches it."""
    method_map = {}
    for rule in horse_recorder.app.url_map.iter_rules():
        method_map.setdefault(rule.rule, set()).update(rule.methods)

    # /api/protocols supports both GET (list) and POST (create)
    assert 'GET' in method_map['/api/protocols']
    assert 'POST' in method_map['/api/protocols']
    # Individual protocol: PUT + DELETE
    assert 'PUT' in method_map['/api/protocols/<protocol_id>']
    assert 'DELETE' in method_map['/api/protocols/<protocol_id>']
    # Favorite toggle: POST only
    assert 'POST' in method_map['/api/protocols/<protocol_id>/favorite']
