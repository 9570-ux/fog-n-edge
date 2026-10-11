import json
import subprocess
import sys
from pathlib import Path

import pytest

from decision import sampling_e2e


def test_isolated_end_to_end_lifecycle_and_fresh_plan(monkeypatch):
    def forbidden_connection(*args, **kwargs):
        pytest.fail('The isolated simulation must never connect to a broker')

    monkeypatch.setattr('paho.mqtt.client.Client.connect', forbidden_connection)
    monkeypatch.setattr('paho.mqtt.client.Client.connect_async', forbidden_connection)
    report = sampling_e2e.run_end_to_end()
    assert report['result'] == 'PASS'
    assert all(report['checks'].values())
    assert report['temporary_database_removed']
    assert report['inspection_matches']
    assert [s['zone_id'] for s in report['plan']['selected']] == ['zone-a', 'zone-c']
    assert all(s['status'] == 'COMPLETED' for s in report['plan']['selected'])
    assert [s['zone_id'] for s in report['fresh_plan']['selected']] == ['zone-mqtt', 'zone-a']
    assert report['initial_empty_plan']['selected'] == []
    assert report['fresh_plan']['request_id'] != report['initial_empty_plan']['request_id']
    evidence = report['simulation_evidence']
    assert len(evidence) == 2
    assert len({e['event_id'] for e in evidence}) == 2
    assert len({e['simulator_run_id'] for e in evidence}) == 1
    assert all(e['is_simulation'] for e in evidence)
    legacy = next(s for s in report['phase4_samples'] if s['zone_id'] == 'zone-b')
    assert (legacy['status'], legacy['collection_status']) == ('REQUESTED', 'SIMULATED')
    assert all(s['laboratory_status'] == 'NOT_SUBMITTED' for s in report['phase4_samples'])
    assert all(e['laboratory_outcome'] is None for e in report['virtual_executions'])


def test_isolated_runner_cleans_up_and_does_not_hide_failure(monkeypatch):
    paths = []
    original = sampling_e2e.MarineDatabase.__init__

    def capture_path(self, path):
        paths.append(Path(path))
        original(self, path)

    def fail_execution(*args):
        raise RuntimeError('injected virtual execution failure')

    monkeypatch.setattr(sampling_e2e.MarineDatabase, '__init__', capture_path)
    monkeypatch.setattr(sampling_e2e, '_execute_virtual_plan', fail_execution)
    with pytest.raises(RuntimeError, match='injected virtual execution failure'):
        sampling_e2e.run_end_to_end()
    assert len(paths) == 1
    assert not paths[0].exists()
    assert paths[0].parent.name.startswith('marine-phase5-e2e-')


def test_end_to_end_cli_ignores_configured_database(tmp_path, monkeypatch):
    sentinel = tmp_path / 'must-not-open.db'
    sentinel.write_bytes(b'not a SQLite database; must remain unchanged')
    monkeypatch.setenv('MARINE_DATABASE_PATH', str(sentinel))
    result = subprocess.run(
        [sys.executable, '-m', 'decision.sampling_demo', '--end-to-end'],
        capture_output=True, text=True, check=True,
    )
    report = json.loads(result.stdout)
    assert report['data_kind'] == 'SYNTHETIC_END_TO_END_SIMULATION'
    assert report['result'] == 'PASS'
    assert sentinel.read_bytes() == b'not a SQLite database; must remain unchanged'
