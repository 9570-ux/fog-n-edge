"""Software-only receiver that simulates a future sampling actuator."""

from __future__ import annotations

import logging
import threading
from typing import Any

import paho.mqtt.client as mqtt

from config import (
    MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEPALIVE_SECONDS, MQTT_QOS,
    MQTT_RECONNECT_MAX_SECONDS, MQTT_RECONNECT_MIN_SECONDS,
    SAMPLING_RECEIVER_MQTT_CLIENT_ID,
)
from decision.sampling_manager import (
    build_command_ack, parse_sampling_command,
)
from mqtt.message_utils import serialize_message, topic

LOG = logging.getLogger("sampling_receiver")


class SimulatedSamplingReceiver:
    def __init__(self, client_id: str = SAMPLING_RECEIVER_MQTT_CLIENT_ID) -> None:
        self.client_id = client_id
        self.stopping = threading.Event()
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
