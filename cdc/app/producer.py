import json
from typing import Any

from confluent_kafka import KafkaException, Producer

from config import Settings


class KafkaProducer:
	def __init__(self, settings: Settings) -> None:
		self.producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
		self._errors: list[KafkaException] = []

	def publish(self, topic: str, key: str, payload: dict[str, Any] | None) -> None:
		def callback(error: KafkaException | None, _message: Any) -> None:
			if error is not None:
				self._errors.append(error)

		value = None if payload is None else json.dumps(payload, default=str)
		self.producer.produce(topic, key=key, value=value, callback=callback)
		self.producer.poll(0)

	def flush(self) -> None:
		self.producer.flush()
		if self._errors:
			errors, self._errors = self._errors, []
			raise errors[0]

	def close(self) -> None:
		self.producer.flush()
