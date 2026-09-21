import json
import os
from pathlib import Path


ROOT = Path(__file__).parent
TEMPLATE = ROOT / "templates" / "postgres-sink.json"
OUTPUT = ROOT / "generated"


def main() -> None:
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    tables = [value.strip() for value in os.getenv("CONNECTOR_TABLES", "").split(",") if value.strip()]
    if not tables:
        raise SystemExit("Set CONNECTOR_TABLES to comma-separated schema.table values")
    OUTPUT.mkdir(exist_ok=True)
    for table in tables:
        schema, name = table.split(".", 1)
        connector = dict(template)
        connector["name"] = f"solarwonds-{schema}-{name}-sink"
        connector["config"] = dict(template["config"])
        prefix = os.getenv("KAFKA_TOPIC_PREFIX", "solarwinds")
        target_schema = os.getenv("TARGET_SCHEMA", "solarwinds")
        connector["config"]["topics"] = f"{prefix}.{schema}.{name}".lower()
        connector["config"]["table.name.format"] = f"{target_schema}.{name.lower()}"
        connector["config"]["connection.url"] = (
            f"jdbc:postgresql://{os.getenv('POSTGRES_HOST', 'localhost')}"
            f":{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB', 'postgres')}"
        )
        connector["config"]["connection.user"] = os.getenv("POSTGRES_USER", "postgres")
        connector["config"]["connection.password"] = os.getenv("POSTGRES_PASSWORD", "CHANGE_ME")
        path = OUTPUT / f"{schema}-{name}.json"
        path.write_text(json.dumps(connector, indent=2) + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
