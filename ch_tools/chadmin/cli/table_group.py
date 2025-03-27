import os
import sys
from collections import OrderedDict
from typing import Any

from cloup import Choice, Context, argument, group, option, option_group, pass_context
from cloup.constraints import (
    AnySet,
    If,
    RequireAtLeast,
    accept_none,
    constraint,
    require_all,
)

from ch_tools.chadmin.cli.chadmin_group import Chadmin
from ch_tools.chadmin.cli.table_metadata import (
    check_replica_path_contains_macros,
    get_table_shared_id,
    move_table_local_store,
    parse_table_metadata,
    update_uuid_table_metadata_file,
)
from ch_tools.chadmin.internal.clickhouse_disks import CLICKHOUSE_PATH
from ch_tools.chadmin.internal.system import get_version, match_str_ch_version
from ch_tools.chadmin.internal.table import (
    attach_table,
    delete_detached_table,
    delete_table,
    detach_table,
    get_info_from_system_tables,
    get_table,
    get_table_uuids_from_cluster,
    list_table_columns,
    list_tables,
    materialize_ttl,
)
from ch_tools.chadmin.internal.utils import execute_query
from ch_tools.common import logging
from ch_tools.common.cli.formatting import format_bytes, print_response
from ch_tools.common.clickhouse.config import get_cluster_name

FIELD_FORMATTERS = {
    "disk_size": format_bytes,
    "uncompressed_size": format_bytes,
}


@group("table", cls=Chadmin)
def table_group():
    """Commands to manage tables."""
    pass


@table_group.command("get")
@argument("database_name", metavar="DATABASE")
@argument("table_name", metavar="TABLE")
@option(
    "--active",
    "--active-parts",
    "active_parts",
    is_flag=True,
    help="Account only active data parts.",
)
@pass_context
def get_command(ctx, database_name, table_name, active_parts):
    """
    Get table.
    """
    table = get_table(ctx, database_name, table_name, active_parts=active_parts)
    print_response(
        ctx,
        table,
        default_format="yaml",
        field_formatters=FIELD_FORMATTERS,
    )


@table_group.command("list")
@option(
    "-d",
    "--database",
    "database_pattern",
    help="Filter in tables to output by the specified database name pattern."
    " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
)
@option(
    "--exclude-database",
    "exclude_database_pattern",
    help="Filter out tables to output by the specified database name pattern."
    " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
)
@option(
    "-t",
    "--table",
    "table_pattern",
    help="Filter in tables to output by the specified table name."
    " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
)
@option(
    "--exclude-table",
    "exclude_table_pattern",
    help="Filter out tables to output by the specified table name."
    " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
)
@option(
    "--engine",
    "engine_pattern",
    help="Filter in tables to output by the specified engine."
    " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
)
@option(
    "--exclude-engine",
    "exclude_engine_pattern",
    help="Filter out tables to output by the specified engine."
    " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
)
@option(
    "--read-only",
    "is_readonly",
    is_flag=True,
    help="Filter in tables in read-only state only.",
)
@option(
    "--active",
    "--active-parts",
    "active_parts",
    is_flag=True,
    help="Account only active data parts.",
)
@option(
    "--order-by",
    type=Choice(["size", "parts", "rows"]),
    help="Sorting order.",
)
@option(
    "-l",
    "--limit",
    type=int,
    default=1000,
    help="Limit the max number of objects in the output.",
)
@pass_context
def list_command(ctx, **kwargs):
    """
    List tables.
    """

    def _table_formatter(item):
        return OrderedDict(
            (
                ("database", item["database"]),
                ("name", item["name"]),
                ("disk_size", item["disk_size"]),
                ("partitions", item["partitions"]),
                ("parts", item["parts"]),
                ("rows", item["rows"]),
                ("metadata_mtime", item["metadata_modification_time"]),
                ("engine", item["engine"]),
            )
        )

    tables = list_tables(ctx, **kwargs)
    print_response(
        ctx,
        tables,
        default_format="table",
        table_formatter=_table_formatter,
        field_formatters=FIELD_FORMATTERS,
    )


@table_group.command("columns")
@argument("database_name", metavar="DATABASE")
@argument("table_name", metavar="TABLE")
@pass_context
def columns_command(ctx, database_name, table_name):
    """
    Describe columns for table.
    """
    table_columns = list_table_columns(ctx, database_name, table_name)
    print_response(
        ctx,
        table_columns,
        default_format="table",
        field_formatters=FIELD_FORMATTERS,
    )


@table_group.command("delete")
@argument("database_name", metavar="DATABASE", required=False)
@argument("table_name", metavar="TABLE", required=False)
@constraint(If("database_name", then=require_all), ["table_name"])
@option_group(
    "Table selection options",
    option(
        "-a",
        "--all",
        "_all",
        is_flag=True,
        help="Filter in all tables.",
    ),
    option(
        "-d",
        "--database",
        "database_pattern",
        help="Filter in tables to delete by the specified database name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-database",
        "exclude_database_pattern",
        help="Filter out tables to delete by the specified database name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "-t",
        "--table",
        "table_pattern",
        help="Filter in tables to delete by the specified table name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-table",
        "exclude_table_pattern",
        help="Filter out tables to delete by the specified table name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--engine",
        "engine_pattern",
        help="Filter in tables to delete by the specified engine pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-engine",
        "exclude_engine_pattern",
        help="Filter out tables to delete by the specified engine pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--read-only",
        "is_readonly",
        is_flag=True,
        help="Filter in tables in read-only state only.",
    ),
    constraint=If(
        AnySet("detached", "database_name", "table_name"),
        then=accept_none,
        else_=RequireAtLeast(1),
    ),
)
@option(
    "--cluster",
    "--on-cluster",
    "on_cluster",
    is_flag=True,
    help="Delete tables on all hosts of the cluster.",
)
@option(
    "--sync/--async",
    "sync_mode",
    default=True,
    help="Enable/Disable synchronous query execution.",
)
@option(
    "-n",
    "--dry-run",
    is_flag=True,
    default=False,
    help="Enable dry run mode and do not perform any modifying actions.",
)
@option(
    "--detached",
    is_flag=True,
    help="Delete detached tables (with nonreplicated engine).",
)
@constraint(
    If("detached", then=require_all), ["database_name", "table_name", "sync_mode"]
)
@constraint(If("detached", then=accept_none), ["on_cluster", "dry_run"])
@pass_context
def delete_command(
    ctx,
    _all,
    on_cluster,
    sync_mode,
    dry_run,
    detached,
    database_name,
    table_name,
    **kwargs,
):
    """
    Delete one or several tables.
    """
    cluster = get_cluster_name(ctx) if on_cluster else None

    if detached:
        delete_detached_table(
            ctx,
            database_name=database_name,
            table_name=table_name,
        )
        return

    if database_name and table_name:
        tables = [get_table(ctx, database_name, table_name)]
    else:
        tables = list_tables(ctx, **kwargs)

    for table in tables:
        delete_table(
            ctx,
            database_name=table["database"],
            table_name=table["name"],
            cluster=cluster,
            sync_mode=sync_mode,
            echo=True,
            dry_run=dry_run,
        )


@table_group.command("recreate")
@argument("database_name", metavar="DATABASE", required=False)
@argument("table_name", metavar="TABLE", required=False)
@constraint(If("database_name", then=require_all), ["table_name"])
@option_group(
    "Table selection options",
    option(
        "-a",
        "--all",
        "_all",
        is_flag=True,
        help="Filter in all tables.",
    ),
    option(
        "-d",
        "--database",
        "database_pattern",
        help="Filter in tables to recreate by the specified database name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-database",
        "exclude_database_pattern",
        help="Filter out tables to recreate by the specified database name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "-t",
        "--table",
        "table_pattern",
        help="Filter in tables to recreate by the specified table name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-table",
        "exclude_table_pattern",
        help="Filter out tables to recreate by the specified table name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--engine",
        "engine_pattern",
        help="Filter in tables to recreate by the specified engine pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-engine",
        "exclude_engine_pattern",
        help="Filter out tables to recreate by the specified engine pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--read-only",
        "is_readonly",
        is_flag=True,
        help="Filter in tables in read-only state only.",
    ),
    constraint=If(
        AnySet("database_name", "table_name"),
        then=accept_none,
        else_=RequireAtLeast(1),
    ),
)
@option(
    "-n",
    "--dry-run",
    is_flag=True,
    default=False,
    help="Enable dry run mode and do not perform any modifying actions.",
)
@pass_context
def recreate_command(ctx, _all, database_name, table_name, dry_run, **kwargs):
    """
    Recreate one or several tables.
    """
    if database_name and table_name:
        tables = [get_table(ctx, database_name, table_name)]
    else:
        tables = list_tables(ctx, **kwargs)

    for table in tables:
        delete_table(
            ctx,
            database_name=table["database"],
            table_name=table["name"],
            echo=True,
            dry_run=dry_run,
        )
        execute_query(
            ctx,
            table["create_table_query"],
            echo=True,
            format_=None,
            dry_run=dry_run,
        )


@table_group.command("detach")
@argument("database_name", metavar="DATABASE", required=False)
@argument("table_name", metavar="TABLE", required=False)
@constraint(If("database_name", then=require_all), ["table_name"])
@option_group(
    "Table selection options",
    option(
        "-a",
        "--all",
        "_all",
        is_flag=True,
        help="Filter in all tables.",
    ),
    option(
        "-d",
        "--database",
        "database_pattern",
        help="Filter in tables to detach by the specified database name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-database",
        "exclude_database_pattern",
        help="Filter out tables to detach by the specified database name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "-t",
        "--table",
        "table_pattern",
        help="Filter in tables to detach by the specified table name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-table",
        "exclude_table_pattern",
        help="Filter out tables to detach by the specified table name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--engine",
        "engine_pattern",
        help="Filter in tables to detach by the specified engine pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-engine",
        "exclude_engine_pattern",
        help="Filter out tables to detach by the specified engine pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--read-only",
        "is_readonly",
        is_flag=True,
        help="Filter in tables in read-only state only.",
    ),
    constraint=If(
        AnySet("database_name", "table_name"),
        then=accept_none,
        else_=RequireAtLeast(1),
    ),
)
@option(
    "--cluster",
    "--on-cluster",
    "on_cluster",
    is_flag=True,
    help="Detach tables on all hosts of the cluster.",
)
@option(
    "-n",
    "--dry-run",
    is_flag=True,
    default=False,
    help="Enable dry run mode and do not perform any modifying actions.",
)
@pass_context
def detach_command(
    ctx,
    _all,
    database_name,
    table_name,
    on_cluster,
    dry_run,
    **kwargs,
):
    """
    Detach one or several tables.
    """
    cluster = get_cluster_name(ctx) if on_cluster else None

    if database_name and table_name:
        tables = [get_table(ctx, database_name, table_name)]
    else:
        tables = list_tables(ctx, **kwargs)

    for table in tables:
        detach_table(
            ctx,
            database_name=table["database"],
            table_name=table["name"],
            cluster=cluster,
            echo=True,
            dry_run=dry_run,
        )


@table_group.command("reattach")
@argument("database_name", metavar="DATABASE", required=False)
@argument("table_name", metavar="TABLE", required=False)
@constraint(If("database_name", then=require_all), ["table_name"])
@option_group(
    "Table selection options",
    option(
        "-a",
        "--all",
        "_all",
        is_flag=True,
        help="Filter in all tables.",
    ),
    option(
        "-d",
        "--database",
        "database_pattern",
        help="Filter in tables to reattach by the specified database name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-database",
        "exclude_database_pattern",
        help="Filter out tables to reattach by the specified database name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "-t",
        "--table",
        "table_pattern",
        help="Filter in tables to reattach by the specified table name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-table",
        "exclude_table_pattern",
        help="Filter out tables to reattach by the specified table name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--engine",
        "engine_pattern",
        help="Filter in tables to reattach by the specified engine pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-engine",
        "exclude_engine_pattern",
        help="Filter out tables to reattach by the specified engine pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--read-only",
        "is_readonly",
        is_flag=True,
        help="Filter in tables in read-only state only.",
    ),
    constraint=If(
        AnySet("database_name", "table_name"),
        then=accept_none,
        else_=RequireAtLeast(1),
    ),
)
@option(
    "--cluster",
    "--on-cluster",
    "on_cluster",
    is_flag=True,
    help="Reattach tables on all hosts of the cluster.",
)
@option(
    "-n",
    "--dry-run",
    is_flag=True,
    default=False,
    help="Enable dry run mode and do not perform any modifying actions.",
)
@pass_context
def reattach_command(
    ctx,
    _all,
    database_name,
    table_name,
    on_cluster,
    dry_run,
    **kwargs,
):
    """
    Reattach one or several tables.
    """
    cluster = get_cluster_name(ctx) if on_cluster else None

    if database_name and table_name:
        tables = [get_table(ctx, database_name, table_name)]
    else:
        tables = list_tables(ctx, **kwargs)

    for table in tables:
        detach_table(
            ctx,
            database_name=table["database"],
            table_name=table["name"],
            cluster=cluster,
            echo=True,
            dry_run=dry_run,
        )
        attach_table(
            ctx,
            database_name=table["database"],
            table_name=table["name"],
            cluster=cluster,
            echo=True,
            dry_run=dry_run,
        )


@table_group.command("attach")
@argument("database_name", metavar="DATABASE")
@argument("table_name", metavar="TABLE")
@option(
    "--cluster",
    "--on-cluster",
    "on_cluster",
    is_flag=True,
    help="Reattach tables on all hosts of the cluster.",
)
@option(
    "-n",
    "--dry-run",
    is_flag=True,
    default=False,
    help="Enable dry run mode and do not perform any modifying actions.",
)
@pass_context
def attach_command(ctx, database_name, table_name, on_cluster, dry_run):
    """
    Attach table.
    """
    cluster = get_cluster_name(ctx) if on_cluster else None
    attach_table(ctx, database_name, table_name, cluster=cluster, dry_run=dry_run)


@table_group.command("materialize-ttl")
@argument("database_name", metavar="DATABASE", required=False)
@argument("table_name", metavar="TABLE", required=False)
@constraint(If("database_name", then=require_all), ["table_name"])
@option_group(
    "Table selection options",
    option(
        "-a",
        "--all",
        "_all",
        is_flag=True,
        help="Filter in all tables.",
    ),
    option(
        "-d",
        "--database",
        "database_pattern",
        help="Filter in tables to materialize TTL by the specified database name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-database",
        "exclude_database_pattern",
        help="Filter out tables to materialize TTL by the specified database name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "-t",
        "--table",
        "table_pattern",
        help="Filter in tables to materialize TTL by the specified table name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-table",
        "exclude_table_pattern",
        help="Filter out tables to materialize TTL by the specified table name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--engine",
        "engine_pattern",
        help="Filter in tables to materialize TTL by the specified engine pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-engine",
        "exclude_engine_pattern",
        help="Filter out tables to materialize TTL by the specified engine pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--read-only",
        "is_readonly",
        is_flag=True,
        help="Filter in tables in read-only state only.",
    ),
    constraint=If(
        AnySet("database_name", "table_name"),
        then=accept_none,
        else_=RequireAtLeast(1),
    ),
)
@option(
    "-n",
    "--dry-run",
    is_flag=True,
    default=False,
    help="Enable dry run mode and do not perform any modifying actions.",
)
@pass_context
def materialize_ttl_command(ctx, _all, database_name, table_name, dry_run, **kwargs):
    """
    Materialize TTL for one or several tables.
    """
    if database_name and table_name:
        tables = [get_table(ctx, database_name, table_name)]
    else:
        tables = list_tables(ctx, **kwargs)

    for table in tables:
        materialize_ttl(
            ctx,
            database_name=table["database"],
            table_name=table["name"],
            echo=True,
            dry_run=dry_run,
        )


@table_group.command("set-flag")
@argument("flag")
@option_group(
    "Table selection options",
    option(
        "-a",
        "--all",
        "_all",
        is_flag=True,
        help="Filter in all tables.",
    ),
    option(
        "-d",
        "--database",
        "database_pattern",
        help="Filter in tables to set the flag by the specified database name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-database",
        "exclude_database_pattern",
        help="Filter out tables to set the flag by the specified database name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "-t",
        "--table",
        "table_pattern",
        help="Filter in tables to set the flag by the specified table name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-table",
        "exclude_table_pattern",
        help="Filter out tables to set the flag by the specified table name pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--engine",
        "engine_pattern",
        help="Filter in tables to set the flag by the specified engine pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--exclude-engine",
        "exclude_engine_pattern",
        help="Filter out tables to set the flag by the specified engine pattern."
        " The value can be either a pattern in the LIKE clause format or a comma-separated list of items to match.",
    ),
    option(
        "--read-only",
        "is_readonly",
        is_flag=True,
        help="Filter in tables in read-only state only.",
    ),
    constraint=RequireAtLeast(1),
)
@option(
    "-v",
    "--verbose",
    type=bool,
    is_flag=True,
    default=True,
    help="Show tables and flag paths.",
)
@pass_context
def set_flag_command(
    ctx: Context,
    _all: bool,
    flag: str,
    verbose: bool,
    **kwargs: Any,
) -> None:
    """
    Create a flag with the specified name inside the data directory of the table.
    """
    tables = list_tables(ctx, **kwargs)
    data_paths = [table["data_paths"][0] for table in tables]
    flag_paths = [os.path.join(data_path, flag) for data_path in data_paths]

    for flag_path in flag_paths:
        with open(flag_path, "a", encoding="utf-8") as _:
            pass

    if verbose:
        for table_, flag_path in zip(tables, flag_paths):
            logging.info("{}: {}", table_["name"], flag_path)


def verify_possible_change_uuid(
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


@table_group.command("change")
@option("-d", "--database", required=True)
@option("-t", "--table", required=True)
@option("-uuid", "--uuid", required=True)
@pass_context
def change_uuid_command(ctx, database, table, uuid):
    table_info = get_info_from_system_tables(ctx, database, table)

    old_table_uuid = table_info["uuid"]
    table_local_metadata_path = table_info["metadata_path"]

    if match_str_ch_version(get_version(ctx), "25.1"):
        table_local_metadata_path = CLICKHOUSE_PATH + "/" + table_local_metadata_path

    verify_possible_change_uuid(ctx, table_local_metadata_path, uuid)
    detach_table(ctx, database_name=database, table_name=table, permanently=False)
    update_uuid_table_metadata_file(table_local_metadata_path, uuid)

    try:
        move_table_local_store(old_table_uuid, uuid)
    except Exception as ex:
        logging.error(
            "Failed move_table_local_store. old uuid={}, new_uuid={}. Need restore uuid in metadata for table={}. error={}",
            old_table_uuid,
            uuid,
            f"{database}.{table}",
            ex,
        )
        sys.exit(1)


@table_group.command("check-uuid-equal")
@option("-d", "--database", required=True)
@option("-t", "--table", required=True)
@pass_context
def check_uuid_equal(ctx, database, table):
    uuids = get_table_uuids_from_cluster(ctx, database, table)
    logging.info("Table {} has uuid: {}", table, uuids)

    if len(uuids) > 1:
        logging.error("Table {} has different uuid in cluster", table)
        sys.exit(1)
