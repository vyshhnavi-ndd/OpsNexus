import pyexasol

c = pyexasol.connect(
    dsn="127.0.0.1:8563",
    user="sys",
    password="exasol",
    encryption=True,
    websocket_sslopt={"cert_reqs": 0},
)

print("pipeline sample", c.execute("SELECT * FROM HACKATHON.PIPELINE_RUNS").fetchall())
print("quality sample", c.execute("SELECT * FROM HACKATHON.DATA_QUALITY_RESULTS").fetchall())
print("kpi sample", c.execute("SELECT * FROM HACKATHON.KPI_HISTORY").fetchall())
print("trust sample", c.execute("SELECT * FROM HACKATHON.TRUST_SCORES").fetchall())

print("\ncolumn identity:")
try:
    print(
        c.execute(
            "SELECT COLUMN_NAME, COLUMN_IDENTITY FROM SYS.EXA_ALL_COLUMNS "
            "WHERE COLUMN_SCHEMA='HACKATHON'"
        ).fetchall()
    )
except Exception as e:
    print("identity col", str(e)[:400])
    print(
        c.execute(
            "SELECT COLUMN_NAME FROM SYS.EXA_ALL_COLUMNS "
            "WHERE COLUMN_SCHEMA='HACKATHON' AND COLUMN_TABLE='PIPELINE_RUNS'"
        ).fetchall()
    )
    cols = c.execute(
        "SELECT * FROM SYS.EXA_ALL_COLUMNS WHERE COLUMN_SCHEMA='HACKATHON' AND COLUMN_TABLE='PIPELINE_RUNS' LIMIT 1"
    )
    print("colnames", cols.column_names() if hasattr(cols, "column_names") else None)
    row = cols.fetchone()
    print("row", row)

c.close()
