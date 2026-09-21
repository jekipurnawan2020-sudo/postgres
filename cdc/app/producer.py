import json
from typing import Any

from confluent_kafka import KafkaException, Producer

from config import Settings


class KafkaProducer:
    def __init__(self, settings: Settings) -> None:
        self.producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})

    def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        errors: list[KafkaException] = []

        def callback(error: KafkaException | None, _message: Any) -> None:
            if error is not None:
                errors.append(error)

        self.producer.produce(topic, key=key, value=json.dumps(payload, default=str), callback=callback)
        self.producer.poll(0)
        self.producer.flush()
        if errors:
            raise errors[0]

    def close(self) -> None:
        self.producer.flush()
