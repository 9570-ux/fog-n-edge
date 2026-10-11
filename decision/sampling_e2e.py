"""Isolated Phase 5 end-to-end simulation; no external broker or production DB."""
from __future__ import annotations

from contextlib import closing, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
from queue import Queue, Empty
from tempfile import TemporaryDirectory
import threading
from time import monotonic
from types import SimpleNamespace

from database import MarineDatabase
from database.diagnostics import inspect_database
from decision import DecisionEngine, SamplingManager
from decision.adaptive_sampling import AdaptiveSamplingPlanner
from mqtt.fog_receiver import FogReceiver
from mqtt.sampling_receiver import SimulatedSamplingReceiver
from mqtt.message_utils import build_sensor_message, serialize_message, topic
from risk import EdgeRiskEngine
from simulator import MarineSensorSimulator
from validation import SensorValidator


class _DemoSamplingManager(SamplingManager):
    @staticmethod
    def build_command(sample: dict) -> dict:
        # Short timer only in this disposable runner; project config is unchanged.
        return {**SamplingManager.build_command(sample), 'duration_seconds': 0.05}


def _sensor_message(zone: str, scenario: str, sequence: int = 1) -> dict:
    event = MarineSensorSimulator(device_id=f'synthetic-{zone}', zone_id=zone, seed=8).generate(scenario)
    event['sequence_number'] = sequence
    validation = SensorValidator().validate(event)
    return build_sensor_message(event, validation, EdgeRiskEngine().calculate(event, validation))


def _seed_legacy_fixture(database: MarineDatabase) -> dict:
    """Explicit synthetic historical fixture; defaults leave completion unknown."""
    message = _sensor_message('zone-b', 'high')
    _, event_id = database.insert_event(message)
    decision = DecisionEngine().decide(message)
    with closing(database._connect()) as connection, connection:
        connection.execute('''INSERT INTO decisions
            (decision_id,sensor_event_id,device_id,zone_id,decision_timestamp,risk_score,
             risk_level,action,reason,sampling_required,priority,status)
            VALUES ('SYNTHETIC-LEGACY-DEC',?,?,?,?,?,?,?,?,?,?,?)''',
            (event_id,message['device_id'],message['zone_id'],message['timestamp'],
             decision['risk_score'],decision['risk_level'],decision['action'],
             decision['reason'],1,decision['priority'],'SAMPLE_REQUESTED'))
        connection.execute('''INSERT INTO samples
            (sample_id,decision_id,sensor_event_id,device_id,zone_id,requested_at,
             trigger_reason,risk_level,risk_score,command_status)
            VALUES ('SYNTHETIC-LEGACY-SAMPLE','SYNTHETIC-LEGACY-DEC',?,?,?,?,?,?,?,'PUBLISHED')''',
            (event_id,message['device_id'],message['zone_id'],message['timestamp'],
             'SYNTHETIC_LEGACY_FIXTURE',decision['risk_level'],decision['risk_score']))
    return next(sample for sample in database.samples() if sample['sample_id'] == 'SYNTHETIC-LEGACY-SAMPLE')


class _InProcessMQTT:
    """Queue JSON messages through real callbacks without connecting Paho clients."""
    def __init__(self, database: MarineDatabase, fog: FogReceiver, receiver: SimulatedSamplingReceiver):
        self.database, self.fog, self.receiver = database, fog, receiver
        self.queue: Queue = Queue()
        self.deliveries: list[dict] = []

    def publish(self, channel: str, payload: str, qos: int):
        self.queue.put((channel, payload))
        return SimpleNamespace(rc=0)

    def sensor(self, message: dict) -> None:
        incoming = SimpleNamespace(topic=topic(message['zone_id'], 'sensors'), payload=serialize_message(message).encode())
        self.fog._on_message(self, None, incoming)

    def deliver_one(self, timeout: float = 2.0) -> None:
        channel, payload = self.queue.get(timeout=timeout)
        incoming = SimpleNamespace(topic=channel, payload=payload.encode())
        if channel.endswith('/commands'):
            self.receiver._on_message(self, None, incoming)
        elif channel.endswith(('/command-ack', '/simulation-events')):
            self.fog._on_message(self, None, incoming)
            message = json.loads(payload)
            sample = next((s for s in self.database.samples() if s['sample_id'] == message['sample_id']), None)
            self.deliveries.append({'topic': channel, 'message': message, 'sample_after_delivery': sample})
        elif not channel.endswith('/ack'):
            raise RuntimeError(f'Unexpected isolated topic: {channel}')

    def complete_new_request(self, sample_id: str) -> None:
        deadline = monotonic() + 3
        while monotonic() < deadline:
            sample = next(s for s in self.database.samples() if s['sample_id'] == sample_id)
            if sample['collection_status'] == 'SIMULATED_COMPLETED':
                return
            try:
                self.deliver_one(timeout=max(0.001, deadline - monotonic()))
            except Empty:
                break
        raise RuntimeError('Isolated MQTT simulation did not persist valid completion before timeout')


def _execute_virtual_plan(planner: AdaptiveSamplingPlanner, plan: dict) -> list[dict]:
    """Execute explicit local virtual timer tasks using the existing plan lifecycle."""
    executions = []
    for item in plan['selected']:
        planner.transition(plan['plan_id'], item['zone_id'], 'IN_PROGRESS')
        started = datetime.now(timezone.utc).isoformat()
        timer = monotonic()
        # Actual local task; no physical collection or lab measurements.
        threading.Event().wait(0.02)
        finished = datetime.now(timezone.utc).isoformat()
        elapsed = monotonic() - timer
        planner.transition(plan['plan_id'], item['zone_id'], 'COMPLETED')
        executions.append({'zone_id': item['zone_id'], 'is_simulation': True,
                           'task': 'LOCAL_VIRTUAL_TIMER', 'started_at': started,
                           'completed_at': finished, 'elapsed_seconds': elapsed,
                           'laboratory_outcome': None})
    return executions


def run_end_to_end() -> dict:
    """Reproduce blockers, perform virtual execution, and prove fresh planning."""
    # There is deliberately no database-path argument or external-broker mode.
    with TemporaryDirectory(prefix='marine-phase5-e2e-') as directory, redirect_stdout(StringIO()):
        path = Path(directory) / 'synthetic.db'
        database = MarineDatabase(path)
        legacy_before = _seed_legacy_fixture(database)
        fog = FogReceiver(database)
        fog.sampling_manager = _DemoSamplingManager()
        receiver = SimulatedSamplingReceiver()
        bus = _InProcessMQTT(database, fog, receiver)
        planner = AdaptiveSamplingPlanner(database, weights={'risk':0.5,'trend':0.15,'overdue':0.2,'quality_proxy':0.15})
        try:
            bus.sensor(_sensor_message('zone-mqtt', 'high'))
            new_sample = next(s for s in database.samples() if s['zone_id'] == 'zone-mqtt')
            empty = planner.generate(2, request_id='synthetic-e2e-empty')
            bus.sensor(_sensor_message('zone-a', 'medium'))
            bus.sensor(_sensor_message('zone-c', 'normal'))
            plan = planner.generate(2, request_id='synthetic-e2e-cycle-001')
            cached_empty = planner.generate(2, request_id='synthetic-e2e-empty')
            bus.complete_new_request(new_sample['sample_id'])
            executions = _execute_virtual_plan(planner, plan)
            completed_plan = planner.inspect(plan['plan_id'])[0]
            fresh = planner.generate(2, request_id='synthetic-e2e-cycle-002')
            diagnostics = inspect_database(path)
            samples = database.samples()
            legacy_after = next(s for s in samples if s['sample_id'] == legacy_before['sample_id'])
            mqtt_sample = next(s for s in samples if s['sample_id'] == new_sample['sample_id'])
            with closing(database._connect()) as connection:
                evidence = [dict(row) for row in connection.execute('SELECT * FROM simulation_events ORDER BY recorded_at,event_id')]
            ack_snapshots = [d['sample_after_delivery'] for d in bus.deliveries if d['message'].get('status') == 'SIMULATED_ACK']
            checks = {
                'initial_block_reproduced': empty['selected'] == [] and set(empty['snapshot']['blocked_zones']) == {'zone-b','zone-mqtt'},
                'cached_empty_not_reused_for_fresh_plan': cached_empty == empty and fresh['plan_id'] != empty['plan_id'],
                'adaptive_budget_and_order': [i['zone_id'] for i in plan['selected']] == ['zone-a','zone-c'],
                'ack_did_not_complete_request': bool(ack_snapshots) and all(s['status'] == 'REQUESTED' and s['collection_status'] == 'SIMULATED_PENDING' for s in ack_snapshots),
                'mqtt_completion_evidenced': mqtt_sample['status'] == 'COMPLETED' and mqtt_sample['collection_status'] == 'SIMULATED_COMPLETED' and len(evidence) == 2,
                'virtual_plan_completed': len(completed_plan['selected']) == 2 and all(i['status'] == 'COMPLETED' and i['completed_at'] and i['sample_id'].startswith('VIRTUAL-') for i in completed_plan['selected']),
                'fresh_plan_includes_released_zone': [i['zone_id'] for i in fresh['selected']] == ['zone-mqtt','zone-a'],
                'legacy_record_unchanged_and_blocked': legacy_before == legacy_after and 'zone-b' in fresh['snapshot']['blocked_zones'],
                'no_lab_or_physical_collection': all(s['laboratory_status'] == 'NOT_SUBMITTED' and s['collection_status'] != 'COLLECTED' for s in samples),
                'sqlite_integrity': diagnostics['integrity'] == 'ok' and diagnostics['foreign_key_errors'] == 0,
            }
            failures = [key for key, passed in checks.items() if not passed]
            if failures:
                raise RuntimeError(f'Isolated end-to-end verification failed: {failures}')
            report = {'data_kind':'SYNTHETIC_END_TO_END_SIMULATION','result':'PASS',
                      'database_scope':'Disposable temporary database; production and backup never opened.',
                      'transport':'In-process MQTT JSON callback simulation; no external broker connection.',
                      'checks':checks,'initial_empty_plan':empty,'plan':completed_plan,
                      'virtual_executions':executions,'fresh_plan':fresh,'phase4_samples':samples,
                      'simulation_evidence':evidence,'mqtt_deliveries':bus.deliveries,
                      'inspection_matches':planner.inspect(plan['plan_id']) == [completed_plan],
                      'limitations':['Virtual timer tasks are not real collection, laboratory results, or HAB detection.',
                                     'Phase 5 tasks use its local lifecycle; Phase 4 commands use the separate validated MQTT evidence lifecycle.',
                                     'This verifies callbacks and JSON routing, not a live Mosquitto connection.',
                                     'IDs, timestamps and measured latency vary; seeded zone selection is reproducible.']}
        finally:
            receiver.stopping.set()
    report['temporary_database_removed'] = not path.exists()
    if not report['temporary_database_removed']:
        raise RuntimeError('Disposable end-to-end database was not cleaned up')
    return report
