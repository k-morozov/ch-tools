import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from ch_tools.chadmin.cli import metadata
from ch_tools.chadmin.internal.clickhouse_disks import CLICKHOUSE_METADATA_PATH


class DatabaseEngine(Enum):
    ATOMIC = "Atomic"
    REPLICATED = "Replicated"

    def is_replicated(self) -> bool:
        return self == DatabaseEngine.REPLICATED


@dataclass
class DatabaseMetadata:
    database_name: str
    database_uuid: str
    database_engine: DatabaseEngine
    replica_path: Optional[str] = None
    shard: Optional[str] = None
    replica_name: Optional[str] = None

    def set_engine_from(self, db_metadata: "DatabaseMetadata") -> None:
        self.database_engine = db_metadata.database_engine
        self.replica_path = db_metadata.replica_path
        self.shard = db_metadata.shard
        self.replica_name = db_metadata.replica_name

    def update_metadata_file(self):
        file_path = db_metadata_path(self.database_name)

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if self.database_engine == DatabaseEngine.REPLICATED:
            engine_line = f"ENGINE = Replicated('{self.replica_path}', '{self.shard}', '{ self.replica_name}')"
        else:
            engine_line = "ENGINE = Atomic"

        lines[1] = engine_line

        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)


def db_metadata_path(database_name: str) -> str:
    return CLICKHOUSE_METADATA_PATH + f"/{database_name}.sql"


def parse_database_from_metadata(database_name: str) -> DatabaseMetadata:
    database_metadata_path = db_metadata_path(database_name)

    assert database_metadata_path.endswith(".sql")
    database_uuid = None
    database_engine = None
    replica_path = None
    shard = None
    replica_name = None

    with open(database_metadata_path, "r", encoding="utf-8") as metadata_file:
        for line in metadata_file:
            if line.startswith("ATTACH DATABASE") and metadata.UUID_TOKEN in line:
                assert database_uuid is None
                database_uuid = metadata.parse_uuid(line)
            if line.startswith("ENGINE ="):
                assert database_engine is None
                database_engine = _parse_engine(line)
                if database_engine.is_replicated():
                    replica_path, shard, replica_name = _parse_database_replica_params(
                        line
                    )

    if database_uuid is None:
        raise RuntimeError(f"Empty UUID from metadata: '{database_metadata_path}'")

    if database_engine is None:
        raise RuntimeError(
            f"Empty database engine from metadata: '{database_metadata_path}'"
        )

    return DatabaseMetadata(
        database_name,
        database_uuid,
        database_engine,
        replica_path=replica_path,
        shard=shard,
        replica_name=replica_name,
    )


def _parse_engine(line: str) -> DatabaseEngine:
    pattern = re.compile(r"ENGINE = (\w+)")

    match = pattern.search(line)
    if not match:
        raise RuntimeError(f"Failed parse {metadata.ENGINE_TOKEN} from metadata.")

    return DatabaseEngine(match.group(1))


def _parse_database_replica_params(line: str) -> Tuple[str, str, str]:
    pattern = r"'([^']*)'"
    matches = re.findall(pattern, line)

    if len(matches) != 3:
        raise ValueError(
            "Failed parse metadata for replicated engine: {}".format(len(matches))
        )
    return matches[0], matches[1], matches[2]
