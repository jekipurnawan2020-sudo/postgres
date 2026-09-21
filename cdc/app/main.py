import logging
import time

from cdc_reader import CdcReader
from checkpoint import CheckpointStore
from config import load_settings
from metadata import Metadata
from producer import KafkaProducer
from schema_builder import build_event
from sqlserver import SqlServer
from topic_manager import TopicManager
from utils import lsn_to_text, operation_name


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
		reader = CdcReader(sqlserver, settings.cdc_batch_size)
		logger.info("CDC reader started for %d capture instances", len(tables))
		while True:
			for table in tables:
				previous_lsn = checkpoints.get(table.capture_instance)
				rows = reader.read(table.capture_instance, previous_lsn)
				for row in rows:
					current_lsn = lsn_to_text(row["__$start_lsn"])
					event = build_event(row, operation_name(row["__$operation"]), f"{table.schema}.{table.table}")
					producer.publish(TopicManager(settings).topic_name(table), current_lsn, event)
					checkpoints.save(table.capture_instance, current_lsn)
			time.sleep(settings.cdc_poll_interval)
	finally:
		producer.close()
		checkpoints.close()
		sqlserver.close()


if __name__ == "__main__":
	run()
