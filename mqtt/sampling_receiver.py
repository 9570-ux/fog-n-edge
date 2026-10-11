"""Software-only receiver that simulates a future sampling actuator."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from uuid import uuid4
import threading
from typing import Any

import paho.mqtt.client as mqtt

from config import (
    MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEPALIVE_SECONDS, MQTT_QOS,
    MQTT_RECONNECT_MAX_SECONDS, MQTT_RECONNECT_MIN_SECONDS,
    SAMPLING_RECEIVER_MQTT_CLIENT_ID,
)
from decision.sampling_manager import (
    build_command_ack, build_simulation_event, parse_sampling_command,
)
from mqtt.message_utils import serialize_message, topic

LOG = logging.getLogger("sampling_receiver")


class SimulatedSamplingReceiver:
    def __init__(self, client_id: str = SAMPLING_RECEIVER_MQTT_CLIENT_ID) -> None:
        self.client_id = client_id
        self.stopping = threading.Event()
        self._simulation_lock = threading.Lock()
        self._simulation_runs: dict[str, dict[str, Any]] = {}
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
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
            subscription = topic("+", "commands")
            client.subscribe(subscription, qos=MQTT_QOS)
            LOG.info("Connected. Subscribed to %s", subscription)
        else:
            LOG.error("MQTT connection rejected: %s", reason_code)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any,
                       disconnect_flags: Any, reason_code: Any, properties: Any) -> None:
        if self.stopping.is_set():
            LOG.info("Sampling simulator stopped cleanly.")
        elif reason_code != 0:
            LOG.warning("Sampling simulator connection lost (%s); Paho will retry.", reason_code)

    def _on_message(self, client: mqtt.Client, userdata: Any,
                    incoming: mqtt.MQTTMessage) -> None:
        try:
            command = parse_sampling_command(incoming.payload)
        except ValueError as exc:
            LOG.warning("Invalid sampling command ignored: %s", exc)
            return
        if str(getattr(incoming, "topic", "")) != topic(command["zone_id"], "commands"):
            LOG.warning("Sampling command topic identity mismatch")
            return
        print("\nSIMULATED SAMPLING COMMAND RECEIVED")
        print(f"Sample ID : {command['sample_id']}")
        print(f"Zone      : {command['zone_id']}")
        print(f"Reason    : {command['reason']}")
        print("Status    : SIMULATED")
        acknowledgement = build_command_ack(command)
        client.publish(
            topic(command["zone_id"], "command-ack"),
            serialize_message(acknowledgement), qos=MQTT_QOS,
        )
        if command.get("simulation_lifecycle") is True:
            self._schedule_simulation(client, command)

    def _publish_evidence(self, client: mqtt.Client, event: dict[str, Any]) -> None:
        try:
            result = client.publish(topic(event["zone_id"], "simulation-events"),
                                    serialize_message(event), qos=MQTT_QOS)
            if getattr(result, "rc", mqtt.MQTT_ERR_SUCCESS) != mqtt.MQTT_ERR_SUCCESS:
                LOG.error("Simulation evidence publication failed: %s", event["event_id"])
        except Exception:
            LOG.exception("Simulation evidence publication failed")

    def _schedule_simulation(self, client: mqtt.Client, command: dict[str, Any]) -> None:
        with self._simulation_lock:
            run = self._simulation_runs.get(command["sample_id"])
            if run is not None:
                if run["command"] != command:
                    LOG.warning("Contradictory duplicate simulation command rejected")
                    return
                replay = [run["start"]] + ([run["completion"]] if run["completion"] else [])
                new_run = False
            else:
                start = build_simulation_event(command, "SIMULATION_STARTED", str(uuid4()),
                                               datetime.now(timezone.utc).isoformat())
                run = {"command": dict(command), "start": start, "completion": None}
                self._simulation_runs[command["sample_id"]] = run
                replay = [start]
                new_run = True
        for event in replay:
            self._publish_evidence(client, event)
        if new_run:
            threading.Thread(target=self._execute_simulation, args=(client, run), daemon=True).start()

    def _execute_simulation(self, client: mqtt.Client, run: dict[str, Any]) -> None:
        # This is a virtual timer task, never a pump or physical collection.
        # Shutdown interrupts the task and deliberately emits no completion.
        if self.stopping.wait(run["command"]["duration_seconds"]):
            return
        start = run["start"]
        completion = build_simulation_event(run["command"], "SIMULATION_COMPLETED",
                                            start["simulator_run_id"], start["started_at"],
                                            datetime.now(timezone.utc).isoformat())
        with self._simulation_lock:
            run["completion"] = completion
        self._publish_evidence(client, completion)

    def run(self) -> None:
        LOG.info("Connecting sampling simulator to %s:%s with client ID %s...",
                 MQTT_BROKER_HOST, MQTT_BROKER_PORT, self.client_id)
        try:
            self.client.connect_async(
                MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEPALIVE_SECONDS
            )
            self.client.loop_forever(retry_first_connection=True)
        except KeyboardInterrupt:
            LOG.info("Sampling simulator stopped by user.")
        finally:
            self.stopping.set()
            self.client.disconnect()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    SimulatedSamplingReceiver().run()


if __name__ == "__main__":
    main()
