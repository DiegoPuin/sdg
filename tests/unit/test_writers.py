import datetime

import pandas as pd
import pytest

from mdf.config import FileOutput
from mdf.context import RunContext
from mdf.errors import WriteError
from mdf.storage import Connections, Storage
from mdf.writers import table_writer as tw
from mdf.writers.file_writer import write_file


@pytest.fixture
def ctx(tmp_path):
    return RunContext({}, Connections(), Storage(local_root=str(tmp_path)))


def out(mode, partition=None):
    cfg = {"path": "/data/out", "format": "parquet", "save_mode": mode}
    if partition:
        cfg["partition"] = partition
    return FileOutput(name="o", type="file", input="x", config=cfg)


def read_all(ctx):
    return pd.read_parquet(ctx.storage.path("/data/out"))


def test_overwrite_and_append(ctx):
    df = pd.DataFrame({"a": [1, 2, 3]})
    write_file(out("overwrite"), df, ctx)
    write_file(out("overwrite"), df, ctx)
    assert len(read_all(ctx)) == 3
    write_file(out("append"), df, ctx)
    assert len(read_all(ctx)) == 6


def test_partition(ctx):
    d1, d2 = datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)
    df = pd.DataFrame({"a": [1, 2, 3], "load_date": [d1, d1, d2]})
    write_file(out("append", "load_date"), df, ctx)
    write_file(out("append", "load_date"), df, ctx)
    import os

    base = ctx.storage.path("/data/out")
    assert sorted(os.listdir(base)) == ["load_date=2024-01-01", "load_date=2024-01-02"]
    assert len(read_all(ctx)) == 6


def test_partition_missing_column(ctx):
    with pytest.raises(WriteError):
        write_file(out("append", "zzz"), pd.DataFrame({"a": [1]}), ctx)


def test_pg_types():
    df = pd.DataFrame(
        {
            "i": [1],
            "f": [1.5],
            "t": ["x"],
            "d": [datetime.date(2024, 1, 1)],
            "ts": [datetime.datetime(2024, 1, 1, 1)],
            "b": [True],
            "ts2": pd.to_datetime(["2024-01-01"]),
        }
    )
    assert tw.column_types(df) == {
        "i": "bigint",
        "f": "double precision",
        "t": "text",
        "d": "date",
        "ts": "timestamp",
        "b": "boolean",
        "ts2": "timestamp",
    }


def test_sql_generation():
    cols = ["province", "sex", "total"]
    assert tw.create_table_sql("demo", {"province": "text", "total": "bigint"}, ["province"]) == (
        'CREATE TABLE IF NOT EXISTS "demo" ("province" text, "total" bigint, '
        'PRIMARY KEY ("province"))'
    )
    assert "PRIMARY KEY" not in tw.create_table_sql("demo", {"a": "text"}, None)
    assert tw.append_sql("raw", cols) == (
        'INSERT INTO "raw" ("province", "sex", "total") SELECT "province", "sex", "total" '
        'FROM "_mdf_stage"'
    )
    assert tw.truncate_sql("raw") == 'TRUNCATE "raw"'
    assert tw.copy_sql(cols).startswith('COPY "_mdf_stage" ("province"')
    assert "ON COMMIT DROP" in tw.create_staging_sql("demo")
    m = tw.merge_sql("demo", cols, ["province", "sex"])
    assert 'ON CONFLICT ("province", "sex") DO UPDATE SET "total" = EXCLUDED."total"' in m
    assert 'WHERE ("demo"."total") IS DISTINCT FROM (EXCLUDED."total")' in m
    assert tw.merge_sql("demo", ["a"], ["a"]).endswith("DO NOTHING")
    c = tw.merge_counts_sql("demo", cols, ["province", "sex"])
    assert "LEFT JOIN" in c and "IS DISTINCT FROM" in c
    assert tw.merge_counts_sql("demo", ["a"], ["a"]).count("FALSE") == 2
    assert tw.qi('a"b') == '"a""b"'


def test_validate_unique_key():
    df = pd.DataFrame({"k": [1, 1, 2], "v": [1, 2, 3]})
    with pytest.raises(WriteError, match="no es única"):
        tw.validate_unique_key(df, ["k"])
    with pytest.raises(WriteError, match="inexistentes"):
        tw.validate_unique_key(df, ["zzz"])
    tw.validate_unique_key(df, ["k", "v"])


def test_rows_converts_nulls():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", None]})
    assert tw._rows(df) == [(1, "x"), (2, None)]


def test_write_table_requires_dsn_and_unique_key(ctx):
    from mdf.config import TableOutput

    node = TableOutput(
        name="t",
        type="table",
        input="x",
        config={"table": "t", "save_mode": "merge", "primary_key": ["k"]},
    )
    with pytest.raises(WriteError, match="no es única"):
        tw.write_table(node, pd.DataFrame({"k": [1, 1]}), ctx)
    with pytest.raises(WriteError, match="WAREHOUSE_DSN"):
        tw.write_table(node, pd.DataFrame({"k": [1, 2]}), ctx)
