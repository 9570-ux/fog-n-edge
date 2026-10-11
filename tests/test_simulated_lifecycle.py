"""Synthetic lifecycle evidence and planner tests; disposable databases only."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import threading

import pytest

from database import MarineDatabase
from database.db import SCHEMA
from database.diagnostics import inspect_database
from decision import DecisionEngine, SamplingManager
from decision.adaptive_sampling import AdaptiveSamplingPlanner
from decision.sampling_manager import build_command_ack, build_simulation_event, parse_simulation_event
from mqtt.fog_receiver import FogReceiver
from mqtt.sampling_receiver import SimulatedSamplingReceiver
from mqtt.message_utils import topic, serialize_message
from tests.test_phase4_decision_sampling import message


@pytest.fixture
def fixture(tmp_path):
    db = MarineDatabase(tmp_path / 'synthetic-lifecycle.db')
    request = db.process_event(message('HIGH'), DecisionEngine(), SamplingManager())
    started = build_simulation_event(request['command'], 'SIMULATION_STARTED', 'synthetic-run', datetime.now(timezone.utc).isoformat())
    completed = build_simulation_event(request['command'], 'SIMULATION_COMPLETED', 'synthetic-run', started['started_at'], datetime.now(timezone.utc).isoformat())
    return db, request, started, completed


def evidence_count(db):
    with closing(db._connect()) as c:
        return c.execute('SELECT COUNT(*) FROM simulation_events').fetchone()[0]


def test_new_states_ack_and_time_do_not_resolve_but_evidence_releases_and_fresh_plan_selects(fixture):
    db, request, started, completed = fixture
    sample = request['sample']
    assert sample['collection_status'] == 'SIMULATED_PENDING'
    assert request['command']['simulation_lifecycle'] is True
    planner = AdaptiveSamplingPlanner(db)
    empty = planner.generate(2, request_id='cycle-001')
    assert empty['selected'] == []
    db.update_sample_command_ack(sample['sample_id'], 'SIMULATED_ACK', device_id=sample['device_id'])
    assert planner.generate(2, now=datetime.now(timezone.utc) + timedelta(days=10))['selected'] == []
    db.insert_event(message('LOW', sequence=2))
    assert planner.generate(2)['selected'] == []
    db.record_simulation_event(started)
    in_progress = db.samples()[0]
    assert in_progress['status'] == 'REQUESTED' and in_progress['collection_status'] == 'SIMULATED_IN_PROGRESS'
    assert planner.generate(2)['selected'] == []
    result = db.record_simulation_event(completed)
    assert result['inserted']
    sample = result['sample']
    assert sample['status'] == 'COMPLETED' and sample['collection_status'] == 'SIMULATED_COMPLETED'
    assert sample['command_status'] == 'SIMULATED_ACK' and sample['laboratory_status'] == 'NOT_SUBMITTED'
    assert planner.generate(2, request_id='cycle-001') == empty
    fresh = planner.generate(2, request_id='cycle-002')
    assert [item['zone_id'] for item in fresh['selected']] == [sample['zone_id']]
    assert fresh['selected'][0]['status'] == 'PLANNED' and fresh['selected'][0]['sample_id'] is None


def test_other_outstanding_request_keeps_zone_blocked(fixture):
    db, request, started, completed = fixture
    db.process_event(message('LOW', sequence=2), DecisionEngine(), SamplingManager())
    second = db.process_event(message('HIGH', sequence=3), DecisionEngine(), SamplingManager())
    db.record_simulation_event(started)
    db.record_simulation_event(completed)
    planner = AdaptiveSamplingPlanner(db)
    assert planner.generate(1)['selected'] == []
    second_start = build_simulation_event(second['command'], 'SIMULATION_STARTED', 'synthetic-run-2', datetime.now(timezone.utc).isoformat())
    second_end = build_simulation_event(second['command'], 'SIMULATION_COMPLETED', 'synthetic-run-2', second_start['started_at'], datetime.now(timezone.utc).isoformat())
    db.record_simulation_event(second_start)
    db.record_simulation_event(second_end)
    assert len(planner.generate(1)['selected']) == 1
    assert db.samples()[0]['command_status'] == second['sample']['command_status']


def test_exact_duplicates_are_idempotent_before_and_after_completion(fixture):
    db, request, started, completed = fixture
    assert db.record_simulation_event(started)['inserted']
    before = db.path.read_bytes()
    assert not db.record_simulation_event(started)['inserted']
    assert db.path.read_bytes() == before
    db.record_simulation_event(completed)
    before = db.path.read_bytes()
    assert not db.record_simulation_event(completed)['inserted']
    assert not db.record_simulation_event(started)['inserted']
    assert db.path.read_bytes() == before
    assert evidence_count(db) == 2


@pytest.mark.parametrize('field,value', [('device_id','wrong'),('zone_id','other-zone'),('sample_id','unknown')])
def test_identity_mismatch_leaves_evidence_and_sample_unchanged(fixture,field,value):
    db, request, started, completed = fixture
    before = db.samples()
    with pytest.raises(ValueError, match='identity'):
        db.record_simulation_event({**started, field:value})
    assert db.samples() == before and evidence_count(db) == 0


def test_completion_requires_start_evidence(fixture):
    db, request, started, completed = fixture
    with pytest.raises(ValueError, match='start evidence'):
        db.record_simulation_event(completed)
    assert db.samples()[0] == request['sample'] and evidence_count(db) == 0


@pytest.mark.parametrize('mutation', ['run','start_time','event_id_conflict','different_stage_id'])
def test_contradictory_evidence_rejected(fixture,mutation):
    db, request, started, completed = fixture
    db.record_simulation_event(started)
    bad = dict(completed)
    if mutation == 'run':
        bad['simulator_run_id'] = 'different-run'
    elif mutation == 'start_time':
        bad['started_at'] = (datetime.fromisoformat(started['started_at']) + timedelta(microseconds=1)).isoformat()
        bad['completed_at'] = datetime.now(timezone.utc).isoformat()
    elif mutation == 'event_id_conflict':
        bad['event_id'] = started['event_id']
    else:
        bad = {**started, 'event_id':'different-id'}
    before = db.path.read_bytes()
    with pytest.raises(ValueError):
        db.record_simulation_event(bad)
    assert db.path.read_bytes() == before and evidence_count(db) == 1


@pytest.mark.parametrize('mutation', ['false_marker','numeric_marker','naive_time','future_time','before_request','reverse_time'])
def test_invalid_marker_and_timestamps_do_not_transition(fixture,mutation):
    db, request, started, completed = fixture
    bad = dict(started)
    if mutation == 'false_marker':
        bad['is_simulation'] = False
    elif mutation == 'numeric_marker':
        bad['is_simulation'] = 1
    elif mutation == 'naive_time':
        bad['started_at'] = '2026-01-01T00:00:00'
    elif mutation == 'future_time':
        bad['started_at'] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    elif mutation == 'before_request':
        bad['started_at'] = (datetime.fromisoformat(request['sample']['requested_at']) - timedelta(seconds=1)).isoformat()
    else:
        bad = {**completed, 'completed_at':(datetime.fromisoformat(started['started_at']) - timedelta(seconds=1)).isoformat()}
    with pytest.raises(ValueError):
        db.record_simulation_event(bad)
    assert db.samples()[0] == request['sample'] and evidence_count(db) == 0


def test_atomic_rollback_if_lifecycle_update_fails(fixture):
    db, request, started, completed = fixture
    db.record_simulation_event(started)
    with closing(db._connect()) as c, c:
        c.execute("CREATE TRIGGER synthetic_failure BEFORE UPDATE OF collection_status ON samples WHEN NEW.collection_status = 'SIMULATED_COMPLETED' BEGIN SELECT RAISE(ABORT, 'synthetic update failure'); END")
    before = db.samples()
    with pytest.raises(sqlite3.IntegrityError):
        db.record_simulation_event(completed)
    assert db.samples() == before and evidence_count(db) == 1


def test_legacy_unknown_requests_reject_start_and_migration_preserves_rows(fixture,tmp_path):
    db, request, started, completed = fixture
    # Explicit synthetic reconstruction of a pre-lifecycle database.
    with closing(db._connect()) as c, c:
        c.execute("UPDATE samples SET collection_status = 'SIMULATED'")
        c.execute('DROP TABLE simulation_events')
    before = db.samples()
    MarineDatabase(db.path)  # Additive migration only in this disposable DB.
    assert db.samples() == before
    assert 'simulation_lifecycle' not in SamplingManager.build_command(before[0])
    with pytest.raises(ValueError, match='legacy'):
        db.record_simulation_event(started)
    assert db.samples() == before and evidence_count(db) == 0
    report = inspect_database(db.path)
    assert report['legacy_simulation_completion_unknown'] == 1
    assert report['evidenced_virtual_completions'] == 0


def test_read_only_diagnostics_distinguishes_evidence_from_legacy(fixture):
    db, request, started, completed = fixture
    db.record_simulation_event(started)
    db.record_simulation_event(completed)
    before = db.path.read_bytes()
    report = inspect_database(db.path)
    assert db.path.read_bytes() == before
    assert report['legacy_simulation_completion_unknown'] == 0
    assert report['evidenced_virtual_completions'] == 1
    assert report['outstanding_sample_requests'] == 0
    assert sum(row['count'] for row in report['simulation_evidence_counts']) == 2


def test_fog_event_handler_records_evidence_without_publishing(fixture,caplog):
    db, request, started, completed = fixture
    class NoPublish:
        def publish(self,*args,**kwargs):
            pytest.fail('Lifecycle handling must not publish commands')
    receiver = FogReceiver(db)
    def send(event, channel_topic):
        incoming = type('Incoming',(),{'topic':channel_topic,'payload':serialize_message(event).encode()})()
        receiver._on_message(NoPublish(),None,incoming)
    send(started,topic('wrong-zone','simulation-events'))
    assert evidence_count(db) == 0 and 'rejected' in caplog.text
    for event in (started,completed,completed):
        send(event,topic(event['zone_id'],'simulation-events'))
    assert evidence_count(db) == 2 and db.samples()[0]['status'] == 'COMPLETED'


class FakeClient:
    def __init__(self):
        self.published = []
        self.completed = threading.Event()
    def publish(self,channel,payload,qos):
        event=json.loads(payload)
        self.published.append((channel,event))
        if event.get('event_type') == 'SIMULATION_COMPLETED':
            self.completed.set()
        return type('Result',(),{'rc':0})()


def test_receiver_separates_ack_timed_task_and_replays_same_event_ids(fixture):
    db, request, started, completed = fixture
    receiver=SimulatedSamplingReceiver()
    command={**request['command'],'duration_seconds':0}
    incoming=type('Incoming',(),{'topic':topic(command['zone_id'],'commands'),'payload':serialize_message(command).encode()})()
    client=FakeClient()
    receiver._on_message(client,None,incoming)
    assert client.completed.wait(2)
    assert client.published[0][1]['status'] == 'SIMULATED_ACK'
    events=[event for channel,event in client.published if event.get('event_type')]
    assert [event['event_type'] for event in events] == ['SIMULATION_STARTED','SIMULATION_COMPLETED']
    for event in events:
        db.record_simulation_event(parse_simulation_event(serialize_message(event)))
    receiver._on_message(client,None,incoming)
    replay=[event for channel,event in client.published if event.get('event_type')][2:]
    assert replay == events
    assert db.samples()[0]['collection_status'] == 'SIMULATED_COMPLETED'
    receiver.stopping.set()


def test_interrupted_virtual_task_never_emits_completion(fixture):
    db,request,started,completed=fixture
    receiver=SimulatedSamplingReceiver()
    receiver.stopping.set()
    client=FakeClient()
    command={**request['command'],'duration_seconds':0}
    incoming=type('Incoming',(),{'topic':topic(command['zone_id'],'commands'),'payload':serialize_message(command).encode()})()
    receiver._on_message(client,None,incoming)
    assert not client.completed.wait(0.05)
    assert all(event.get('event_type') != 'SIMULATION_COMPLETED' for channel,event in client.published)


@pytest.mark.parametrize('field,value', [('duration_seconds', -1), ('duration_seconds', True),
    ('duration_seconds', float('nan')), ('device_id', []), ('simulation_lifecycle', False),
    ('requested_at', 'bad'), ('zone_id', '#')])
def test_explicit_simulation_command_validation_rejects_bad_task_inputs(fixture,field,value):
    from decision.sampling_manager import parse_sampling_command
    db,request,started,completed=fixture
    with pytest.raises(ValueError):
        parse_sampling_command(serialize_message({**request['command'],field:value}))
