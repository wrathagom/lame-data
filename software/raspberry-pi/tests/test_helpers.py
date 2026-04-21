"""Tests for pure helpers: protocol load/save, _normalize_steps, _find_protocol.

These exercise code paths the API tests also hit, but at the function level
where failures are easier to pinpoint.
"""
import json

import horse_recorder


def test_load_protocols_seeds_defaults_on_first_run(isolated_paths):
    """Fresh install (no protocols.json) should create one with the seed."""
    assert not isolated_paths['protocols_file'].exists()

    data = horse_recorder.load_protocols()

    assert isolated_paths['protocols_file'].exists()
    assert len(data['protocols']) == 1
    assert data['protocols'][0]['name'] == 'Standard Lameness Exam'
    assert data['protocols'][0]['is_favorite'] is True
    assert len(data['protocols'][0]['steps']) == 8


def test_load_protocols_does_not_overwrite_existing(isolated_paths):
    """Existing file must be preserved exactly, not reseeded on read."""
    custom = {'protocols': [{'id': 'x', 'name': 'Custom', 'is_favorite': False, 'steps': []}]}
    horse_recorder.save_protocols(custom)

    loaded = horse_recorder.load_protocols()
    assert loaded == custom


def test_save_protocols_writes_pretty_json(isolated_paths):
    """Indented JSON makes the file human-editable on the Pi if needed."""
    horse_recorder.save_protocols({'protocols': []})
    raw = isolated_paths['protocols_file'].read_text()
    assert '\n' in raw  # indent=2 means multiline


def test_normalize_steps_drops_empty_instructions():
    result = horse_recorder._normalize_steps([
        {'instruction': 'keep me'},
        {'instruction': ''},
        {'instruction': '   '},
        {'instruction': 'also keep'},
    ])
    assert [s['instruction'] for s in result] == ['keep me', 'also keep']


def test_normalize_steps_assigns_missing_ids():
    result = horse_recorder._normalize_steps([
        {'instruction': 'no id here'},
    ])
    assert result[0]['id'].startswith('s-')
    assert len(result[0]['id']) > 2


def test_normalize_steps_preserves_existing_ids():
    result = horse_recorder._normalize_steps([
        {'id': 'keep-this', 'instruction': 'hello'},
    ])
    assert result[0]['id'] == 'keep-this'


def test_normalize_steps_strips_extra_fields():
    """Protect the on-disk schema: unknown keys shouldn't sneak in."""
    result = horse_recorder._normalize_steps([
        {'id': 's1', 'instruction': 'walk', 'malicious': 'field'},
    ])
    assert set(result[0].keys()) == {'id', 'instruction'}


def test_normalize_steps_trims_whitespace():
    result = horse_recorder._normalize_steps([
        {'instruction': '  walk in hand  '},
    ])
    assert result[0]['instruction'] == 'walk in hand'


def test_normalize_steps_handles_none_and_empty():
    assert horse_recorder._normalize_steps(None) == []
    assert horse_recorder._normalize_steps([]) == []


def test_find_protocol_returns_match():
    data = {'protocols': [
        {'id': 'a', 'name': 'A'},
        {'id': 'b', 'name': 'B'},
    ]}
    assert horse_recorder._find_protocol(data, 'b')['name'] == 'B'


def test_find_protocol_returns_none_for_missing():
    assert horse_recorder._find_protocol({'protocols': []}, 'nope') is None
    assert horse_recorder._find_protocol({}, 'nope') is None


def test_load_device_config_returns_default_when_missing(isolated_paths):
    """Same robustness as protocols — first boot shouldn't crash."""
    config = horse_recorder.load_device_config()
    assert 'devices' in config
    assert 'positions' in config
