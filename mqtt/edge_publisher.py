"""Simulated Edge publisher reusing the complete Phase 1 pipeline."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

from config import (
    DEVICE_ID, EDGE_MQTT_CLIENT_ID, EDGE_PUBLISH_INTERVAL_SECONDS,
    MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEPALIVE_SECONDS, MQTT_QOS,
    MQTT_RECONNECT_MAX_SECONDS, MQTT_RECONNECT_MIN_SECONDS,
    OFFLINE_QUEUE_PATH, ZONE_ID,
)
from mqtt.message_utils import (
    OfflineQueue, build_sensor_message, parse_ack, serialize_message, topic,
)
from risk import EdgeRiskEngine
from simulator import MarineSensorSimulator
from validation import SensorValidator

LOG = logging.getLogger("edge_publisher")


class EdgePublisher:
    def __init__(self, client_id: str = EDGE_MQTT_CLIENT_ID,
                 queue: OfflineQueue | None = None) -> None:
        self.simulator = MarineSensorSimulator()
        self.validator = SensorValidator()
        self.engine = EdgeRiskEngine()
        self.queue = queue or OfflineQueue(OFFLINE_QUEUE_PATH)
        queued = self.queue.read_all()
        if queued:
            own_sequences = [
                item["sequence_number"] for item in queued
                if item.get("device_id") == DEVICE_ID
            ]
            if own_sequences:
                self.simulator.sequence_number = max(own_sequences)
        self.connected = threading.Event()
        self.stopping = threading.Event()
        self.ever_connected = False
        self.client_id = client_id
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=self.client_id)
        self.client.will_set(topic(ZONE_ID, "status"), "OFFLINE", qos=MQTT_QOS, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(
            min_delay=MQTT_RECONNECT_MIN_SECONDS,
            max_delay=MQTT_RECONNECT_MAX_SECONDS,
        )

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any,
                    reason_code: Any, properties: Any) -> None:
        if reason_code != 0:
            LOG.error("MQTT connection rejected: %s", reason_code)
            return
        state = "RECONNECTED" if self.ever_connected else "ONLINE"
        self.ever_connected = True
        self.connected.set()
        client.subscribe(topic(ZONE_ID, "ack"), qos=MQTT_QOS)
        client.publish(topic(ZONE_ID, "status"), state, qos=MQTT_QOS, retain=True)
        LOG.info("Connected to MQTT broker (%s).", state)
        self.replay_queue()

    def _on_disconnect(self, client: mqtt.Client, userdata: Any,
                       disconnect_flags: Any, reason_code: Any, properties: Any) -> None:
        self.connected.clear()
        if self.stopping.is_set():
            LOG.info("Disconnected from MQTT broker (intentional shutdown).")
        elif reason_code != 0:
            LOG.warning(
                "Unexpected MQTT disconnect (%s). Check broker health and ensure "
                "client ID %s is not running in another Edge terminal. Paho will "
                "retry with bounded delay.", reason_code, self.client_id,
            )
        else:
            LOG.info("Disconnected from MQTT broker.")

    def _on_message(self, client: mqtt.Client, userdata: Any, incoming: mqtt.MQTTMessage) -> None:
        try:
            acknowledgement = parse_ack(incoming.payload)
        except ValueError as exc:
            LOG.warning("Invalid acknowledgement ignored: %s", exc)
            return
        if acknowledgement["device_id"] != DEVICE_ID:
            return
        if acknowledgement["status"] in {"RECEIVED", "DUPLICATE"}:
            removed = self.queue.remove(DEVICE_ID, acknowledgement["sequence_number"])
            if removed:
                LOG.info("Fog acknowledged sequence %s; removed from offline queue.",
                         acknowledgement["sequence_number"])

    def publish_message(self, message: dict[str, Any]) -> None:
        self.queue.append(message)
        if not self.connected.is_set():
            LOG.warning("MQTT unavailable; sequence %s safely queued.", message["sequence_number"])
            return
        self._publish(message)

    def _publish(self, message: dict[str, Any]) -> None:
        payload = serialize_message(message)
        result = self.client.publish(topic(message["zone_id"], "sensors"), payload, qos=MQTT_QOS)
        self.client.publish(topic(message["zone_id"], "edge-risk"), payload, qos=MQTT_QOS)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            LOG.info("Published sequence %s (awaiting Fog acknowledgement).",
                     message["sequence_number"])
        else:
            LOG.warning("Publish failed for sequence %s; event remains queued.",
                        message["sequence_number"])

    def replay_queue(self) -> None:
        try:
            records = self.queue.read_all()
        except ValueError as exc:
            LOG.error("Offline queue cannot be replayed safely: %s", exc)
            return
        if records:
            LOG.info("Replaying %s queued event(s) in sequence order.", len(records))
        for message in records:
            self._publish(message)

    def run(self) -> None:
        LOG.info("Connecting to MQTT broker at %s:%s with client ID %s...",
                 MQTT_BROKER_HOST, MQTT_BROKER_PORT, self.client_id)
        try:
            self.client.connect_async(MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEPALIVE_SECONDS)
            self.client.loop_start()
            while True:
                event = self.simulator.generate_random()
                validation = self.validator.validate(event)
                risk = self.engine.calculate(event, validation)
                self.publish_message(build_sensor_message(event, validation, risk))
                time.sleep(EDGE_PUBLISH_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            LOG.info("Edge publisher stopped by user.")
        finally:
            self.stopping.set()
            if self.connected.is_set():
                self.client.publish(topic(ZONE_ID, "status"), "OFFLINE", qos=MQTT_QOS,
                                    retain=True).wait_for_publish(timeout=2)
            self.client.disconnect()
            self.client.loop_stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    EdgePublisher().run()


if __name__ == "__main__":
    main()
