import json
import logging
import time
from urllib import error, request

from config import Settings
from metadata import CaptureTable

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _config(self, table: CaptureTable) -> dict[str, str]:
        topic = f"{self.settings.kafka_topic_prefix}.{table.schema}.{table.table}".lower()
        config: dict[str, str] = {
            "connector.class": "io.confluent.connect.jdbc.JdbcSinkConnector",
            "tasks.max": str(self.settings.connector_tasks_max),
            "connection.url": f"jdbc:postgresql://{self.settings.postgres_host}:{self.settings.postgres_port}/{self.settings.postgres_db}",
            "connection.user": self.settings.postgres_user,
            "connection.password": self.settings.postgres_password,
            "topics": topic,
            "table.name.format": f"{self.settings.target_schema}.{table.table.lower()}",
            "auto.create": str(self.settings.connector_auto_create).lower(),
            "auto.evolve": str(self.settings.connector_auto_evolve).lower(),
            "insert.mode": "upsert" if table.primary_keys else "insert",
            "pk.mode": "record_key" if table.primary_keys else "none",
            "key.converter": "org.apache.kafka.connect.json.JsonConverter",
            "key.converter.schemas.enable": "false",
            "value.converter": "org.apache.kafka.connect.json.JsonConverter",
            "value.converter.schemas.enable": "false",
            "delete.enabled": str(bool(table.primary_keys)).lower(),
            "behavior.on.null.values": "delete",
            "quote.identifiers": "true",
        }
        if table.primary_keys:
            config["pk.fields"] = ",".join(table.primary_keys)
        return config

    def register(self, tables: list[CaptureTable]) -> None:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                for table in tables:
                    name = f"{self.settings.kafka_topic_prefix}-{table.schema}-{table.table}-sink".lower()
                    req = request.Request(
                        f"{self.settings.connect_rest_url}/connectors/{name}/config",
                        data=json.dumps(self._config(table)).encode(),
                        headers={"Content-Type": "application/json"},
                        method="PUT",
                    )
                    with request.urlopen(req, timeout=10):
                        pass
                logger.info("Registered %d Kafka Connect sink connectors", len(tables))
                return
            except (error.URLError, TimeoutError, OSError) as exc:
                logger.warning("Kafka Connect not ready: %s", exc)
                time.sleep(5)
        raise RuntimeError("Kafka Connect REST API did not become ready within 180 seconds")
