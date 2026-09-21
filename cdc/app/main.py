import logging
import time
import json

from cdc_reader import CdcReader
from checkpoint import CheckpointStore
from config import load_settings
from connector_registry import ConnectorRegistry
from metadata import Metadata
from producer import KafkaProducer
from initial_load import InitialLoader
from schema_builder import build_event, record_key
from sqlserver import SqlServer
from topic_manager import TopicManager
from utils import lsn_to_text


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run() -> None:
	settings = load_settings()
	sqlserver = SqlServer(settings)
	checkpoints = CheckpointStore(settings)
	producer = KafkaProducer(settings)
	try:
		checkpoints.ensure_table()
		tables = Metadata(sqlserver).capture_tables()
		TopicManager(settings).ensure(tables)
		if settings.register_connectors:
			ConnectorRegistry(settings).register(tables)
		reader = CdcReader(sqlserver, settings.cdc_batch_size)
		loader = InitialLoader(sqlserver, settings.cdc_batch_size)
		logger.info("CDC reader started for %d capture instances", len(tables))
		while True:
			for table in tables:
				previous_lsn = checkpoints.get(table.capture_instance)
				if settings.initial_load_enabled and previous_lsn is None:
					snapshot_lsn = sqlserver.current_lsn()
					for row in loader.stream(table.schema, table.table):
						key = record_key(row, table.primary_keys)
						producer.publish(TopicManager(settings).topic_name(table), json.dumps(key, default=str), build_event(row))
					checkpoints.save(table.capture_instance, snapshot_lsn)
					previous_lsn = snapshot_lsn
				rows = reader.read(table.capture_instance, previous_lsn)
				for row in rows:
					current_lsn = lsn_to_text(row["__$start_lsn"])
					operation = row["__$operation"]
					if operation == 3:
						continue
					key = record_key(row, table.primary_keys)
					event = None if operation == 1 else build_event(row)
					producer.publish(TopicManager(settings).topic_name(table), json.dumps(key, default=str), event)
					checkpoints.save(table.capture_instance, current_lsn)
			time.sleep(settings.cdc_poll_interval)
	finally:
		producer.close()
		checkpoints.close()
		sqlserver.close()


if __name__ == "__main__":
	run()
