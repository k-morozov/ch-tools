import os
import sys
from typing import Dict

from click import ClickException, Context

from ch_tools.chadmin.internal.clickhouse_disks import (
    CLICKHOUSE_DATA_PATH,
    CLICKHOUSE_METADATA_PATH,
    CLICKHOUSE_PATH,
    OBJECT_STORAGE_DISK_TYPES,
    S3_PATH,
    make_ch_disks_config,
    remove_from_ch_disk,
)
from ch_tools.chadmin.internal.system import get_version, match_str_ch_version
from ch_tools.chadmin.internal.table_metadata import (
    check_replica_path_contains_macros,
    get_table_shared_id,
    move_table_local_store,
    parse_table_metadata,
    update_uuid_table_metadata_file,
)
from ch_tools.chadmin.internal.utils import execute_query, remove_from_disk
from ch_tools.chadmin.internal.zookeeper_clean import clean_zk_metadata_for_hosts
from ch_tools.common import logging
from ch_tools.common.clickhouse.client.query_output_format import OutputFormat

DISK_LOCAL_KEY = "local"
DISK_OBJECT_STORAGE_KEY = "object_storage"


def get_table(ctx, database_name, table_name, active_parts=None):
    tables = list_tables(
        ctx,
        database_name=database_name,
        table_name=table_name,
        active_parts=active_parts,
    )

    if not tables:
        raise ClickException(f"Table `{database_name}`.`{table_name}` not found.")

    return tables[0]


def list_tables(
    ctx,
    *,
    database_name=None,
    database_pattern=None,
    exclude_database_pattern=None,
    table_name=None,
    table_pattern=None,
    exclude_table_pattern=None,
    engine_pattern=None,
    exclude_engine_pattern=None,
    is_readonly=None,
    active_parts=None,
    order_by=None,
    limit=None,
):
    order_by = {
        "size": "disk_size DESC",
        "parts": "parts DESC",
        "rows": "rows DESC",
        None: "database, name",
    }[order_by]
    query = """
        WITH tables AS (
            SELECT
                t.database,
                t.name,
                t.metadata_modification_time,
                t.engine,
                t.data_paths,
                t.create_table_query
            FROM system.tables t
        {% if is_readonly -%}
            LEFT JOIN system.replicas r ON r.database = t.database AND r.table = t.name
        {% endif -%}
            WHERE true
        {% if database_name -%}
            AND t.database = '{{ database_name }}'
        {% endif -%}
        {% if database_pattern -%}
            AND t.database {{ format_str_match(database_pattern) }}
        {% endif -%}
        {% if not database_name and not database_pattern  -%}
            AND t.database NOT IN ('system', 'information_schema', 'INFORMATION_SCHEMA')
        {% endif -%}
        {% if exclude_database_pattern -%}
            AND t.database NOT {{ format_str_match(exclude_database_pattern) }}
        {% endif -%}
        {% if table_name -%}
            AND t.name = '{{ table_name }}'
        {% endif -%}
        {% if table_pattern -%}
            AND t.name {{ format_str_match(table_pattern) }}
        {% endif -%}
        {% if exclude_table_pattern -%}
            AND t.name NOT {{ format_str_match(exclude_table_pattern) }}
        {% endif -%}
        {% if engine_pattern -%}
            AND t.engine {{ format_str_match(engine_pattern) }}
        {% endif -%}
        {% if exclude_engine_pattern -%}
           AND t.engine NOT {{ format_str_match(exclude_engine_pattern) }}
        {% endif -%}
        {% if is_readonly -%}
           AND r.is_readonly
        {% endif -%}
        ),
        parts AS (
            SELECT
                p.database,
                p.table,
                uniq(p.partition) "partitions",
                count() "parts",
                sum(p.rows) "rows",
                sum(p.bytes_on_disk) "disk_size"
            FROM system.parts p
            JOIN tables t ON t.database = p.database AND t.name = p.table
        {% if active_parts -%}
            WHERE p.active
        {% endif -%}
            GROUP BY p.database, p.table
        )
        SELECT
            t.database,
            t.name,
            t.engine,
            t.create_table_query,
            t.metadata_modification_time,
            t.data_paths,
            p.disk_size,
            p.partitions,
            p.parts,
            p.rows
        FROM tables t
        LEFT JOIN parts p ON p.database = t.database AND p.table = t.name
        ORDER BY {{ order_by }}
        {% if limit is not none -%}
        LIMIT {{ limit }}
        {% endif -%}
        """
    return execute_query(
        ctx,
        query,
        database_name=database_name,
        database_pattern=database_pattern,
        exclude_database_pattern=exclude_database_pattern,
        table_name=table_name,
        table_pattern=table_pattern,
        exclude_table_pattern=exclude_table_pattern,
        engine_pattern=engine_pattern,
        exclude_engine_pattern=exclude_engine_pattern,
        is_readonly=is_readonly,
        active_parts=active_parts,
        order_by=order_by,
        limit=limit,
        format_="JSON",
    )["data"]


def list_table_columns(ctx, database_name, table_name):
    query = """
        SELECT
            name,
            type,
            default_kind,
            default_expression,
            data_compressed_bytes "disk_size",
            data_uncompressed_bytes "uncompressed_size",
            marks_bytes
        FROM system.columns
        WHERE database = '{{ database_name }}'
          AND table = '{{ table_name }}'
        """
    return execute_query(
        ctx,
        query,
        database_name=database_name,
        table_name=table_name,
        format_="JSON",
    )["data"]


def detach_table(
    ctx,
    database_name,
    table_name,
    permanently=True,
    *,
    cluster=None,
    echo=False,
    dry_run=False,
):
    """
    Perform "DETACH TABLE" for the specified table.
    """
    # pylint: disable=unused-argument

    logging.info("Detaching table `{}`.`{}`", database_name, table_name)
    timeout = ctx.obj["config"]["clickhouse"]["detach_table_timeout"]
    query = """
        DETACH TABLE `{{ database_name }}`.`{{ table_name }}`
        {%- if cluster %}
        ON CLUSTER '{{ cluster }}'
        {%- endif %}
        {%- if permanently %}
        NO DELAY
        {%- endif %}
        """
    execute_query(
        ctx,
        query,
        timeout=timeout,
        database_name=database_name,
        table_name=table_name,
        cluster=cluster,
        echo=echo,
        dry_run=dry_run,
        format_=None,
    )


def attach_table(
    ctx,
    database_name,
    table_name,
    *,
    cluster=None,
    echo=False,
    dry_run=False,
):
    """
    Perform "ATTACH TABLE" for the specified table.
    """
    logging.info("Attaching table `{}`.`{}`", database_name, table_name)
    timeout = ctx.obj["config"]["clickhouse"]["attach_table_timeout"]
    query = """
        ATTACH TABLE `{{ database_name }}`.`{{ table_name }}`
        {%- if cluster %}
        ON CLUSTER '{{ cluster }}'
        {%- endif %}
        """
    execute_query(
        ctx,
        query,
        timeout=timeout,
        database_name=database_name,
        table_name=table_name,
        cluster=cluster,
        echo=echo,
        dry_run=dry_run,
        format_=None,
    )


def delete_table(
    ctx,
    database_name,
    table_name,
    *,
    cluster=None,
    echo=False,
    sync_mode=True,
    dry_run=False,
):
    """
    Perform "DROP TABLE" for the specified table.
    """
    logging.info("Deleting table `{}`.`{}`", database_name, table_name)
    timeout = ctx.obj["config"]["clickhouse"]["drop_table_timeout"]
    query = """
        DROP TABLE `{{ database_name }}`.`{{ table_name }}`
        {%- if cluster %}
        ON CLUSTER '{{ cluster }}'
        {%- endif %}
        {%- if sync_mode %}
        NO DELAY
        {%- endif %}
        """
    execute_query(
        ctx,
        query,
        timeout=timeout,
        database_name=database_name,
        table_name=table_name,
        cluster=cluster,
        sync_mode=sync_mode,
        echo=echo,
        dry_run=dry_run,
        format_=None,
    )


def check_table_dettached(ctx, database_name, table_name):
    query = """
        SELECT
            1
        FROM system.tables
        WHERE database = '{{ database_name }}'
          AND table = '{{ table_name }}'
    """

    response = execute_query(
        ctx,
        query,
        database_name=database_name,
        table_name=table_name,
        format_="JSON",
    )["data"]

    if len(response):
        raise RuntimeError(
            f"Table '{database_name}'.'{table_name}' is attached. Use delete without --detach flag."
        )


def _assign_disk_type(result: Dict[str, str], key: str, disk_name: str) -> None:
    if key in result:
        raise RuntimeError(f"It's a bug. {key} was set early.")
    result[key] = disk_name


def _get_disks_data(ctx: Context) -> Dict[str, str]:
    # Disk type 'cache' of disk object_storage_cache is not supported by clickhouse-disks
    query = """
        SELECT name, type FROM system.disks
        WHERE name!='object_storage_cache'
    """
    response = execute_query(
        ctx,
        query,
        format_="JSON",
    )["data"]

    logging.info("Found disks: {}", response)

    result: Dict[str, str] = {}

    for data_disk in response:
        if data_disk.get("type") in OBJECT_STORAGE_DISK_TYPES:
            _assign_disk_type(result, DISK_OBJECT_STORAGE_KEY, data_disk["name"])
        else:
            _assign_disk_type(result, DISK_LOCAL_KEY, data_disk["name"])

    logging.info("Table disks: {}", result)

    # Although currently we ensure that no keys in result are overridden,
    # I prefer to add an assert for future possible refactoring. If we skip even one disk,
    # we may never remove the data on it in the future.
    assert len(response) == len(result)
    return result


def _is_should_use_ch_disk_remover(table_data_path: str, disk_type: str) -> bool:
    if disk_type == DISK_LOCAL_KEY:
        return os.path.exists(CLICKHOUSE_PATH + table_data_path)
    if disk_type == DISK_OBJECT_STORAGE_KEY:
        return os.path.exists(S3_PATH + table_data_path)

    return True


def _remove_table_data_from_disk(
    table_uuid: str, disk_name: str, disk_type: str, ch_version: str
) -> None:
    logging.info(
        "_remove_table_data_from_disk: UUID={}, disk={}",
        table_uuid,
        disk_name,
    )

    table_data_path = "store" + "/" + table_uuid[:3] + "/" + table_uuid

    logging.info(
        "Table has UUID: {}, disk: {}, data path: {}.",
        table_uuid,
        disk_name,
        table_data_path,
    )

    disk_config_path = make_ch_disks_config(disk_name)

    if not _is_should_use_ch_disk_remover(table_data_path, disk_type):
        logging.warning(
            f"Dir {table_data_path} doesn't exist on disk {disk_name}. Skip launch clickhouse-disks for Clickhouse 22.8."
        )

    code, stderr = remove_from_ch_disk(
        disk=disk_name,
        path=table_data_path,
        disk_config_path=disk_config_path,
        ch_version=ch_version,
    )
    if code:
        raise RuntimeError(
            f"clickhouse-disks remove command has failed: retcode {code}, stderr: {stderr.decode()}"
        )


def delete_detached_table(ctx, database_name, table_name):
    logging.info("Call delete_detached_table: {}.{}", database_name, table_name)

    escaped_database_name = database_name.encode("unicode_escape").decode("utf-8")
    escaped_table_name = table_name.encode("unicode_escape").decode("utf-8")

    logging.info("Escaped params: {}.{}", escaped_database_name, escaped_table_name)

    check_table_dettached(ctx, escaped_database_name, escaped_table_name)

    local_metadata_table_path = (
        CLICKHOUSE_METADATA_PATH
        + "/"
        + escaped_database_name
        + "/"
        + escaped_table_name
        + ".sql"
    )

    if not os.path.exists(local_metadata_table_path):
        raise RuntimeError(
            f"No metadata file for table '{escaped_database_name}'.'{escaped_table_name}' by path {local_metadata_table_path}."
        )

    table_metadata = parse_table_metadata(local_metadata_table_path)

    for disk_type, disk_name in _get_disks_data(ctx).items():
        _remove_table_data_from_disk(
            table_uuid=table_metadata.table_uuid,
            disk_name=disk_name,
            disk_type=disk_type,
            ch_version=get_version(ctx),
        )

    if table_metadata.table_engine.is_table_engine_replicated():
        logging.info(
            "Remove node: replica_name={}, replica_path={}",
            table_metadata.replica_name,
            table_metadata.replica_path,
        )

        clean_zk_metadata_for_hosts(
            ctx,
            nodes=[table_metadata.replica_name],
            zk_cleanup_root_path=table_metadata.replica_path,
            cleanup_database=False,
            cleanup_ddl_queue=False,
        )

    link_to_local_data = (
        CLICKHOUSE_DATA_PATH + "/" + escaped_database_name + "/" + escaped_table_name
    )
    logging.info("Remove link: {}", link_to_local_data)
    remove_from_disk(link_to_local_data)

    permanently_flag = local_metadata_table_path + ".detached"
    if os.path.exists(permanently_flag):
        logging.info("Remove permanently flag: {}", permanently_flag)
        remove_from_disk(permanently_flag)

    logging.info("Remove table metadata: {}", local_metadata_table_path)
    remove_from_disk(local_metadata_table_path)

    logging.info(
        "Detached table {}.{} deleted.", escaped_database_name, escaped_table_name
    )


def materialize_ttl(ctx, database_name, table_name, echo=False, dry_run=False):
    """
    Materialize TTL for the specified table.
    """
    timeout = ctx.obj["config"]["clickhouse"]["alter_table_timeout"]
    query = f"ALTER TABLE `{database_name}`.`{table_name}` MATERIALIZE TTL"
    execute_query(ctx, query, timeout=timeout, echo=echo, dry_run=dry_run, format_=None)


def get_info_from_system_tables(ctx, database, table):
    query = f"""
        SELECT uuid, metadata_path FROM system.tables WHERE database='{database}' AND table='{table}'
    """
    rows = execute_query(ctx, query, echo=True, format_=OutputFormat.JSON)["data"]

    return rows[0]


def get_table_uuids_from_cluster(ctx: Context, database: str, table: str) -> list:
    query = f"""
        SELECT uuid FROM clusterAllReplicas('{{cluster}}', system.tables) WHERE database='{database}' AND table='{table}'
    """
    rows = execute_query(ctx, query, echo=True, format_=OutputFormat.JSON)["data"]
    return list(set(row["uuid"] for row in rows))


def _verify_possible_change_uuid(
    ctx: Context, table_local_metadata_path: str, dst_uuid: str
) -> None:
    metadata = parse_table_metadata(table_local_metadata_path)

    if metadata.table_engine.is_table_engine_replicated():
        logging.info(
            "Metadata={} with Replicated table engine, replica_name={}, replica_path={}",
            table_local_metadata_path,
            metadata.replica_name,
            metadata.replica_path,
        )
        if check_replica_path_contains_macros(metadata.replica_path, "uuid"):
            logging.error(
                f"Changing uuid for ReplicatedMergeTree that contains macros uuid in replica path was not allowed. replica_path={metadata.replica_path}"
            )
            sys.exit(1)

        table_shared_id = get_table_shared_id(ctx, metadata.replica_path)

        if dst_uuid != table_shared_id:
            logging.error(
                f"Changing uuid for ReplicatedMergeTree that different from table_shared_id path was not allowed. replica_path={metadata.replica_path}, dst_uuid={dst_uuid}, table_shared_id={table_shared_id}"
            )
            sys.exit(1)

    if metadata.table_uuid == dst_uuid:
        logging.error("Table has already had uuid {}", metadata.table_uuid)
        sys.exit(1)


def change_table_uuid(
    ctx: Context,
    database: str,
    table: str,
    new_uuid: str,
    old_table_uuid: str,
    table_local_metadata_path: str,
    attached: bool,
) -> None:
    if match_str_ch_version(get_version(ctx), "25.1"):
        table_local_metadata_path = f"{CLICKHOUSE_PATH}/{table_local_metadata_path}"

    _verify_possible_change_uuid(ctx, table_local_metadata_path, new_uuid)
    if attached:
        detach_table(ctx, database_name=database, table_name=table, permanently=False)
    update_uuid_table_metadata_file(table_local_metadata_path, new_uuid)

    try:
        move_table_local_store(old_table_uuid, new_uuid)
    except Exception as ex:
        logging.error(
            "Failed move_table_local_store. old uuid={}, new_uuid={}. Need restore uuid in metadata for table={}. error={}",
            old_table_uuid,
            new_uuid,
            f"{database}.{table}",
            ex,
        )
        sys.exit(1)


def read_local_table_metadata(ctx: Context, table_local_metadata_path: str) -> str:
    if match_str_ch_version(get_version(ctx), "25.1"):
        table_local_metadata_path = f"{CLICKHOUSE_PATH}/{table_local_metadata_path}"

    with open(table_local_metadata_path, "r", encoding="utf-8") as f:
        return f.read()
