from confluent_kafka.admin import AdminClient, NewTopic

from config import Settings
from metadata import CaptureTable


class TopicManager:
    def __init__(self, settings: Settings) -> None:
        self.prefix = settings.kafka_topic_prefix
        self.admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})

    def topic_name(self, table: CaptureTable) -> str:
        return f"{self.prefix}.{table.schema}.{table.table}".lower()

    def ensure(self, tables: list[CaptureTable]) -> None:
        existing = set(self.admin.list_topics(timeout=10).topics)
        topics = [NewTopic(self.topic_name(table), num_partitions=1, replication_factor=1)
                  for table in tables if self.topic_name(table) not in existing]
        if topics:
            self.admin.create_topics(topics)
