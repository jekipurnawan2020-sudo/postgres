from typing import Any

from sqlserver import SqlServer


class CdcReader:
	def __init__(self, sqlserver: SqlServer, batch_size: int) -> None:
		self.sqlserver = sqlserver
		self.batch_size = batch_size

	def read(self, capture_instance: str, from_lsn: str | None) -> list[dict[str, Any]]:
		if from_lsn:
			query = f'''DECLARE @from_lsn binary(10) = CONVERT(binary(10), ?, 2);
				DECLARE @to_lsn binary(10) = sys.fn_cdc_get_max_lsn();
				SELECT TOP (?) * FROM cdc.fn_cdc_get_all_changes_{capture_instance}
				(@from_lsn, @to_lsn, 'all') ORDER BY __$start_lsn, __$seqval;'''
			return self.sqlserver.query(query, (from_lsn, self.batch_size))
		query = f'''DECLARE @from_lsn binary(10) = sys.fn_cdc_get_min_lsn(?);
			DECLARE @to_lsn binary(10) = sys.fn_cdc_get_max_lsn();
			SELECT TOP (?) * FROM cdc.fn_cdc_get_all_changes_{capture_instance}
			(@from_lsn, @to_lsn, 'all') ORDER BY __$start_lsn, __$seqval;'''
		return self.sqlserver.query(query, (capture_instance, self.batch_size))
