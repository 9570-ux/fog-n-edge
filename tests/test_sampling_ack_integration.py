"""Synthetic ACK integration fixtures; all writes use temporary databases."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import sqlite3

import pytest

from database import MarineDatabase
from database.db import SCHEMA
from database.diagnostics import inspect_database
from decision import DecisionEngine, SamplingManager
from decision.adaptive_sampling import AdaptiveSamplingPlanner
from decision.sampling_manager import build_command_ack, parse_command_ack
from mqtt.fog_receiver import FogReceiver
from mqtt.message_utils import serialize_message, topic
from tests.test_phase4_decision_sampling import message


@pytest.fixture
def sample_database(tmp_path):
    db = MarineDatabase(tmp_path / 'ack.db')
    result = db.process_event(message('HIGH'), DecisionEngine(), SamplingManager())
    return db, result['sample'], result['command']


def send_ack(db, acknowledgement, incoming_topic):
    class NoPublishClient:
        def publish(self, *args, **kwargs):
            pytest.fail('ACK handling must not publish MQTT commands')
    incoming = type('Incoming', (), {'topic': incoming_topic, 'payload': serialize_message(acknowledgement).encode()})()
    FogReceiver(db)._on_message(NoPublishClient(), None, incoming)


def test_valid_and_duplicate_network_ack_preserves_every_lifecycle_field(sample_database):
    db, sample, command = sample_database
    db.update_sample_command_ack(sample['sample_id'], 'PUBLISHED')
    before = db.samples()[0]
    ack = build_command_ack(command)
    send_ack(db, ack, topic(sample['zone_id'], 'command-ack'))
    expected = {**before, 'command_status': 'SIMULATED_ACK'}
    assert db.samples()[0] == expected
    send_ack(db, ack, topic(sample['zone_id'], 'command-ack'))
    assert db.samples()[0] == expected
    # Transport ACKs leave both Phase 4 and Phase 5 eligibility unchanged.
    assert expected['status'] == 'REQUESTED'
    assert expected['collection_status'] == 'SIMULATED_PENDING'
    assert expected['laboratory_status'] == 'NOT_SUBMITTED'
    assert AdaptiveSamplingPlanner(db).generate(2)['selected'] == []


def test_ack_can_arrive_before_local_publication_status_and_late_updates_are_noops(sample_database):
    db, sample, command = sample_database
    send_ack(db, build_command_ack(command), topic(sample['zone_id'], 'command-ack'))
    before = db.samples()
    assert db.update_sample_command_ack(sample['sample_id'], 'PUBLISHED')
    assert db.update_sample_command_ack(sample['sample_id'], 'PENDING')
    assert db.samples() == before
    assert before[0]['command_status'] == 'SIMULATED_ACK'


def test_concurrent_ack_and_publish_never_regress(sample_database):
    db, sample, _ = sample_database
    def update(status):
        return db.update_sample_command_ack(sample['sample_id'], status)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(update, ['SIMULATED_ACK', 'PUBLISHED']))
    assert db.samples()[0]['command_status'] == 'SIMULATED_ACK'


@pytest.mark.parametrize('identity', ['unknown_sample', 'wrong_device', 'wrong_zone', 'wrong_root'])
def test_network_identity_mismatch_is_rejected_without_changes(sample_database, identity, caplog):
    db, sample, command = sample_database
    before = db.samples()
    ack = build_command_ack(command)
    incoming_topic = topic(sample['zone_id'], 'command-ack')
    if identity == 'unknown_sample':
        ack['sample_id'] = 'SAMPLE-UNKNOWN'
    elif identity == 'wrong_device':
        ack['device_id'] = 'unrelated-device'
    elif identity == 'wrong_zone':
        incoming_topic = topic('other-zone', 'command-ack')
    else:
        incoming_topic = 'wrong-root/' + sample['zone_id'] + '/command-ack'
    send_ack(db, ack, incoming_topic)
    assert db.samples() == before
    assert 'acknowledgement rejected' in caplog.text


@pytest.mark.parametrize('field,value', [('sample_id', ''), ('sample_id', []), ('device_id', None),
    ('device_id', ' '), ('timestamp', 'bad'), ('timestamp', '2026-10-11T00:00:00'),
    ('timestamp', 123), ('status', 'COMPLETED')])
def test_invalid_ack_payload_is_rejected(sample_database, field, value):
    db, sample, command = sample_database
    ack = build_command_ack(command)
    ack[field] = value
    with pytest.raises(ValueError):
        parse_command_ack(serialize_message(ack))
    before = db.samples()
    send_ack(db, ack, topic(sample['zone_id'], 'command-ack'))
    assert db.samples() == before


@pytest.mark.parametrize('sample_id,status', [('unknown', 'SIMULATED_ACK'), ('', 'SIMULATED_ACK'),
    ([], 'SIMULATED_ACK'), (None, 'SIMULATED_ACK'), ('existing', 'COMPLETED'), ('existing', [])])
def test_trusted_updater_rejects_invalid_values(sample_database, sample_id, status):
    db, sample, _ = sample_database
    sample_id = sample['sample_id'] if sample_id == 'existing' else sample_id
    before = db.samples()
    assert not db.update_sample_command_ack(sample_id, status)
    assert db.samples() == before


def test_diagnostics_reads_blocked_snapshot_without_writing(sample_database):
    db, sample, _ = sample_database
    db.update_sample_command_ack(sample['sample_id'], 'PUBLISHED')
    plan = AdaptiveSamplingPlanner(db).generate(2, request_id='cycle-001')
    before = hashlib.sha256(db.path.read_bytes()).hexdigest()
    report = inspect_database(db.path)
    assert hashlib.sha256(db.path.read_bytes()).hexdigest() == before
    assert report['outstanding_sample_requests'] == 1
    assert report['command_status_counts'] == [{'command_status': 'PUBLISHED', 'count': 1}]
    assert report['blocked_zones'] == [sample['zone_id']]
    assert report['eligible_zones'] == []
    assert report['current_eligibility_reason'] == 'ALL_OBSERVED_ZONES_BLOCKED'
    assert report['virtual_plans'] == 1 and report['virtual_statuses'] == []
    assert report['plans'][0]['plan_id'] == plan['plan_id']
    assert report['plans'][0]['no_candidates_reason'] == 'STORED_SNAPSHOT_HAS_ONLY_BLOCKED_ZONES'
    assert report['plans'][0]['selected_count'] == 0


def test_diagnostics_distinguishes_zero_budget_from_no_candidates(tmp_path):
    db = MarineDatabase(tmp_path / 'eligible.db')
    db.insert_event(message('LOW'))
    AdaptiveSamplingPlanner(db).generate(0)
    report = inspect_database(db.path)
    assert report['current_eligibility_reason'] == 'ELIGIBLE_ZONES_AVAILABLE'
    assert report['plans'][0]['candidate_count'] == 1
    assert report['plans'][0]['no_candidates_reason'] is None
    assert report['plans'][0]['empty_selection_reason'] == 'ZERO_BUDGET'


def test_diagnostics_handles_missing_phase5_schema_without_migration(tmp_path):
    path = tmp_path / 'legacy.db'
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(SCHEMA.split('-- Phase 5 additive migration')[0])
    before = path.read_bytes()
    report = inspect_database(path)
    assert path.read_bytes() == before
    assert not report['phase5_schema_available']
    assert report['current_eligibility_reason'] == 'NO_OBSERVED_ZONES'
    assert report['virtual_plans'] == 0


def test_diagnostics_does_not_create_a_missing_database(tmp_path):
    path = tmp_path / 'missing.db'
    with pytest.raises(sqlite3.OperationalError):
        inspect_database(path)
    assert not path.exists()
