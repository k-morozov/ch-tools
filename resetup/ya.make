OWNER(g:mdb)

PY3_PROGRAM(ch-resetup)

PY_SRCS(
	MAIN main.py
)

PEERDIR(
    cloud/mdb/clickhouse/tools/common
)

END()
