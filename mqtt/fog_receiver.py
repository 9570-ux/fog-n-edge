"""Simulated Fog MQTT receiver for Phase 2."""

from __future__ import annotations

import logging
import threading
from typing import Any

import paho.mqtt.client as mqtt

from config import (
    FOG_MQTT_CLIENT_ID, MQTT_BROKER_HOST, MQTT_BROKER_PORT,
    MQTT_KEEPALIVE_SECONDS, MQTT_QOS, MQTT_RECONNECT_MAX_SECONDS,
    MQTT_RECONNECT_MIN_SECONDS,
)
from database import MarineDatabase
from decision import DecisionEngine, SamplingManager
from decision.sampling_manager import parse_command_ack
from mqtt.message_utils import (
    DuplicateDetector, build_ack, parse_sensor_message, serialize_message, topic,
)

LOG = logging.getLogger("fog_receiver")


class FogReceiver:
    def __init__(self, database: MarineDatabase | None = None,
                 client_id: str = FOG_MQTT_CLIENT_ID) -> None:
        self.detector = DuplicateDetector()
        self.database = database or MarineDatabase()
        self.decision_engine = DecisionEngine()
        self.sampling_manager = SamplingManager()
        self.client_id = client_id
        self.stopping = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=self.client_id)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(
            min_delay=MQTT_RECONNECT_MIN_SECONDS,
            max_delay=MQTT_RECONNECT_MAX_SECONDS,
        )

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any,
                    reason_code: Any, properties: Any) -> None:
        if reason_code == 0:
            subscription = topic("+", "sensors").replace("/+", "/+")
            client.subscribe(subscription, qos=MQTT_QOS)
            command_ack_subscription = topic("+", "command-ack")
            client.subscribe(command_ack_subscription, qos=MQTT_QOS)
            LOG.info("Connected to MQTT broker. Subscribed to %s and %s",
                     subscription, command_ack_subscription)
        else:
            LOG.error("MQTT connection rejected: %s", reason_code)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any,
                       disconnect_flags: Any, reason_code: Any, properties: Any) -> None:
        if self.stopping.is_set():
            LOG.info("Disconnected from MQTT broker (intentional shutdown).")
        elif reason_code != 0:
            LOG.warning(
                "Unexpected MQTT disconnect (%s). Check broker health and ensure "
                "client ID %s is not running in another Fog terminal. Paho will "
                "retry with bounded delay.", reason_code, self.client_id,
            )
        else:
            LOG.info("Disconnected from MQTT broker.")

    def _on_message(self, client: mqtt.Client, userdata: Any, incoming: mqtt.MQTTMessage) -> None:
        if str(getattr(incoming, "topic", "")).endswith("/command-ack"):
            self._handle_command_ack(incoming.payload)
            return
        try:
            message = parse_sensor_message(incoming.payload)
        except ValueError as exc:
            LOG.warning("INVALID MQTT MESSAGE - Reason: %s", exc)
            return

        # SQLite is the durable source of truth for duplicate detection. Always
        # retry the transaction even when the in-memory detector has seen the
        # sequence, because a previous database attempt may have rolled back.
        memory_duplicate = self.detector.is_duplicate(message)
        try:
            LOG.info(
                "Invoking Phase 4 event/decision transaction: device=%s sequence=%s",
                message["device_id"], message["sequence_number"],
            )
            result = self.database.process_event(
                message, self.decision_engine, self.sampling_manager
            )
        except Exception:
            LOG.exception("PROCESSING ERROR - event not acknowledged and remains queued")
            return
        duplicate = not result["inserted"]
        status = "DUPLICATE" if duplicate else "RECEIVED"
        if duplicate:
            LOG.warning("DUPLICATE MESSAGE IGNORED - Device: %s Sequence: %s",
                        message["device_id"], message["sequence_number"])
        else:
            if memory_duplicate:
                LOG.info("Retry completed after an earlier in-memory observation.")
            LOG.info("Sensor event persisted: event_id=%s", result["event_id"])
            LOG.info(
                "Decision persisted successfully: decision_id=%s action=%s risk=%s",
                result["decision"]["decision_id"], result["decision"]["action"],
                result["decision"]["risk_level"],
            )
            self._display(message)
            self._display_decision(result["decision"], result["sample"])
            if result["command"]:
                LOG.info("Sampling required. Sample created: %s",
                         result["sample"]["sample_id"])
                command_payload = serialize_message(result["command"])
                publish_result = client.publish(
                    topic(message["zone_id"], "commands"), command_payload,
                    qos=MQTT_QOS,
                )
                if getattr(publish_result, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS:
                    self.database.update_sample_command_ack(
                        result["sample"]["sample_id"], "PUBLISHED"
                    )
                    LOG.info("Published simulated sampling command for %s.",
                             result["sample"]["sample_id"])
        acknowledgement = build_ack(message, status)
        client.publish(topic(message["zone_id"], "ack"), serialize_message(acknowledgement),
                       qos=MQTT_QOS)

    def _handle_command_ack(self, payload: bytes | str) -> None:
        try:
            acknowledgement = parse_command_ack(payload)
        except ValueError as exc:
            LOG.warning("Invalid sampling command acknowledgement: %s", exc)
            return
        updated = self.database.update_sample_command_ack(
            acknowledgement["sample_id"], acknowledgement["status"]
        )
        if updated:
            LOG.info("Simulated sampling command acknowledged for %s.",
                     acknowledgement["sample_id"])
        else:
            LOG.warning("Command acknowledgement references unknown sample %s.",
                        acknowledgement["sample_id"])

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

    @staticmethod
    def _display_decision(decision: dict[str, Any], sample: dict[str, Any] | None) -> None:
        print("\nFOG DECISION")
        print(f"Decision ID      : {decision['decision_id']}")
        print(f"Action           : {decision['action']}")
        print(f"Priority         : {decision['priority']}")
        print(f"Reason           : {decision['reason']}")
        print(f"Sampling Required: {'YES' if decision['sampling_required'] else 'NO'}")
        print(f"Decision Status  : {decision['status']}")
        if sample:
            print(f"Sample ID        : {sample['sample_id']}")
        print("========================================")

    def run(self) -> None:
        LOG.info("Active SQLite database: %s", self.database.path)
        LOG.info("Connecting to MQTT broker at %s:%s with client ID %s...",
                 MQTT_BROKER_HOST, MQTT_BROKER_PORT, self.client_id)
        try:
            self.client.connect_async(MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEPALIVE_SECONDS)
            self.client.loop_forever(retry_first_connection=True)
        except KeyboardInterrupt:
            LOG.info("Fog receiver stopped by user.")
        finally:
            self.stopping.set()
            self.client.disconnect()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    FogReceiver().run()


if __name__ == "__main__":
    main()
