"""Simulated Fog MQTT receiver for Phase 2."""

from __future__ import annotations

import logging
import os
from typing import Any

import paho.mqtt.client as mqtt

from config import MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEPALIVE_SECONDS, MQTT_QOS
from database import MarineDatabase
from mqtt.message_utils import (
    DuplicateDetector, build_ack, parse_sensor_message, serialize_message, topic,
)

LOG = logging.getLogger("fog_receiver")


class FogReceiver:
    def __init__(self, database: MarineDatabase | None = None,
                 client_id: str | None = None) -> None:
        self.detector = DuplicateDetector()
        self.database = database or MarineDatabase()
        # A process-specific default avoids MQTT client-ID collisions when an
        # earlier Fog terminal is still running during local development.
        resolved_client_id = client_id or f"marine-fog-node-{os.getpid()}"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=resolved_client_id)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any,
                    reason_code: Any, properties: Any) -> None:
        if reason_code == 0:
            subscription = topic("+", "sensors").replace("/+", "/+")
            client.subscribe(subscription, qos=MQTT_QOS)
            LOG.info("Connected to MQTT broker. Subscribed to %s", subscription)
        else:
            LOG.error("MQTT connection rejected: %s", reason_code)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any,
                       disconnect_flags: Any, reason_code: Any, properties: Any) -> None:
        if reason_code != 0:
            LOG.warning("MQTT connection lost (%s). Client will retry.", reason_code)
        else:
            LOG.info("Disconnected from MQTT broker.")

    def _on_message(self, client: mqtt.Client, userdata: Any, incoming: mqtt.MQTTMessage) -> None:
        try:
            message = parse_sensor_message(incoming.payload)
        except ValueError as exc:
            LOG.warning("INVALID MQTT MESSAGE - Reason: %s", exc)
            return

        duplicate = self.detector.is_duplicate(message)
        status = "DUPLICATE" if duplicate else "RECEIVED"
        if not duplicate:
            try:
                inserted, _ = self.database.insert_event(message)
            except Exception:
                LOG.exception("DATABASE ERROR - event not acknowledged and remains queued")
                return
            if not inserted:
                duplicate = True
                status = "DUPLICATE"
        if duplicate:
            LOG.warning("DUPLICATE MESSAGE IGNORED - Device: %s Sequence: %s",
                        message["device_id"], message["sequence_number"])
        else:
            LOG.info("Stored event in SQLite database.")
            self._display(message)
        acknowledgement = build_ack(message, status)
        client.publish(topic(message["zone_id"], "ack"), serialize_message(acknowledgement),
                       qos=MQTT_QOS)

    @staticmethod
    def _display(message: dict[str, Any]) -> None:
        print("\n========================================")
        print("FOG NODE - MQTT EVENT RECEIVED")
        print("========================================")
        print(f"Device          : {message['device_id']}")
        print(f"Zone            : {message['zone_id']}")
        print(f"Sequence        : {message['sequence_number']}")
        print(f"Temperature     : {message['temperature_c']} deg C")
        print(f"pH              : {message['ph']}")
        print(f"Salinity        : {message['salinity_psu']} PSU")
        print(f"Turbidity       : {message['turbidity_ntu']} NTU")
        print(f"DO              : {message['dissolved_oxygen_mg_l']} mg/L")
        print(f"Sensor Validity : {'VALID' if message['sensor_valid'] else 'INVALID'}")
        print(f"Edge Risk Score : {message['edge_risk_score']} / 100")
        print(f"Edge Risk Level : {message['edge_risk_level']}")
        print("MQTT Status     : RECEIVED")
        print("========================================")

    def run(self) -> None:
        LOG.info("Connecting to MQTT broker at %s:%s...", MQTT_BROKER_HOST, MQTT_BROKER_PORT)
        try:
            self.client.connect_async(MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEPALIVE_SECONDS)
            self.client.loop_forever(retry_first_connection=True)
        except KeyboardInterrupt:
            LOG.info("Fog receiver stopped by user.")
        finally:
            self.client.disconnect()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    FogReceiver().run()


if __name__ == "__main__":
    main()
