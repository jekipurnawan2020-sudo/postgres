import logging
import time
import json

from cdc_reader import CdcReader
from checkpoint import CheckpointStore
from config import load_settings
from connector_registry import ConnectorRegistry
from metadata import CaptureTable, Metadata
from producer import KafkaProducer
from initial_load import InitialLoader
from schema_builder import build_event, record_key
from schema_sync import SchemaSync
from sqlserver import SqlServer
from topic_manager import TopicManager
from utils import lsn_to_text


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def publish_initial_load(producer: KafkaProducer, topic: str, rows, primary_keys: tuple[str, ...], flush_every: int) -> None:
	pending = 0
	for row in rows:
		key = record_key(row, primary_keys)
		producer.publish(topic, json.dumps(key, default=str), build_event(row))
		pending += 1
		if pending >= flush_every:
			producer.flush()
			pending = 0
	if pending:
		producer.flush()


def publish_cdc_batch(producer: KafkaProducer, topic: str, rows: list[dict], table: CaptureTable) -> str | None:
	last_lsn = None
	for row in rows:
		operation = row["__$operation"]
		if operation == 3:
			continue
		key = record_key(row, table.primary_keys)
		event = None if operation == 1 else build_event(row)
		producer.publish(topic, json.dumps(key, default=str), event)
		last_lsn = lsn_to_text(row["__$start_lsn"])
	if last_lsn is not None:
		producer.flush()
	return last_lsn


def run() -> None:
	settings = load_settings()
	sqlserver = SqlServer(settings)
	checkpoints = CheckpointStore(settings)
	producer = KafkaProducer(settings)
	try:
		checkpoints.ensure_table()
		tables = Metadata(sqlserver).capture_tables()
		topics = TopicManager(settings)
		topics.ensure(tables)
		SchemaSync(settings, sqlserver).apply(tables)
		if settings.register_connectors:
			ConnectorRegistry(settings).register(tables)
		reader = CdcReader(sqlserver, settings.cdc_batch_size)
		loader = InitialLoader(sqlserver, settings.cdc_batch_size)
		logger.info("CDC reader started for %d capture instances", len(tables))
		while True:
			for table in tables:
				topic = topics.topic_name(table)
				previous_lsn = checkpoints.get(table.capture_instance)
				if settings.initial_load_enabled and previous_lsn is None:
					snapshot_lsn = sqlserver.current_lsn()
					publish_initial_load(
						producer, topic, loader.stream(table.schema, table.table), table.primary_keys, settings.cdc_batch_size
					)
					checkpoints.save(table.capture_instance, snapshot_lsn)
					previous_lsn = snapshot_lsn
				rows = reader.read(table.capture_instance, previous_lsn)
				last_lsn = publish_cdc_batch(producer, topic, rows, table)
				if last_lsn is not None:
					checkpoints.save(table.capture_instance, last_lsn)
			time.sleep(settings.cdc_poll_interval)
	finally:
		producer.close()
		checkpoints.close()
		sqlserver.close()


if __name__ == "__main__":
	run()
