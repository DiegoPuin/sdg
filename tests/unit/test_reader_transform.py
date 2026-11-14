import datetime

import pandas as pd
import pytest

from mdf.config import (
    AddFieldsTransformation,
    FileInput,
    FilterTransformation,
    GroupTransformation,
)
from mdf.context import RunContext
from mdf.errors import ReadError, TransformError
from mdf.readers.file_reader import csv_kwargs, read_file
from mdf.storage import Connections, Storage
from mdf.transformations.add_fields import apply_add_fields
from mdf.transformations.filter import apply_filter
from mdf.transformations.group import apply_group

CSV = (
    "province;municipality;sex;total\r\n"
    "02 Albacete;02003 Albacete;Men;1.932\r\n"
    "02 Albacete;N/A;Both sexes;9.625\r\n"
    "02 Albacete;N/A;Men;5\r\n"
)


@pytest.fixture
def ctx(tmp_path):
    return RunContext({}, Connections(), Storage(local_root=str(tmp_path)))


def csv_node(path="/data/in.csv", **options):
    opts = {"header": "true", "delimiter": ";", "thousands": ".", **options}
    return FileInput(name="i", type="file", config={"path": path, "format": "csv"}, options=opts)


def put(ctx, rel, text):
    p = ctx.storage.path(rel)
    import os

    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(b"\xef\xbb\xbf" + text.encode())


def test_read_csv_bom_thousands_and_na(ctx):
    put(ctx, "/data/in.csv", CSV)
    df = read_file(csv_node(), ctx)
    assert list(df.columns) == ["province", "municipality", "sex", "total"]
    assert df["total"].tolist() == [1932, 9625, 5]
    assert (df["municipality"] == "N/A").sum() == 2  # N/A se conserva como texto


def test_read_missing_file(ctx):
    with pytest.raises(ReadError):
        read_file(csv_node("/data/missing.csv"), ctx)


def test_csv_kwargs():
    assert csv_kwargs({"header": "false", "delimiter": ",", "thousands": "."}) == {
        "header": None,
        "sep": ",",
        "thousands": ".",
    }
    with pytest.raises(ReadError):
        csv_kwargs({"quote": "x"})


def test_read_parquet(ctx):
    p = ctx.storage.path("/data/pq")
    import os

    os.makedirs(p)
    pd.DataFrame({"a": [1, 2]}).to_parquet(f"{p}/part-0.parquet")
    node = FileInput(name="i", type="file", config={"path": "/data/pq", "format": "parquet"})
    assert read_file(node, ctx)["a"].tolist() == [1, 2]


@pytest.fixture
def df():
    return pd.DataFrame(
        {
            "province": ["A", "A", "B", "B"],
            "municipality": ["m1", "N/A", "m2", "m2"],
            "sex": ["Men", "Men", "Both sexes", "Women"],
            "total": [1, 2, 3, 4],
        }
    )


def test_filter(df):
    node = FilterTransformation(
        name="f",
        type="filter",
        input="x",
        config={"filter": "sex != 'Both sexes' and municipality != 'N/A'"},
    )
    out = apply_filter(node, df)
    assert out["total"].tolist() == [1, 4]


def test_filter_invalid(df):
    node = FilterTransformation(name="f", type="filter", input="x", config={"filter": "zzz ==="})
    with pytest.raises(TransformError):
        apply_filter(node, df)


def test_add_fields(df):
    node = AddFieldsTransformation(
        name="a",
        type="add_fields",
        input="x",
        config={
            "fields": [
                {"name": "domain", "expression": "'demography'"},
                {"name": "load_date", "expression": "current_date()"},
                {"name": "k", "expression": "7"},
                {"name": "dbl", "expression": "total * 2"},
            ]
        },
    )
    out = apply_add_fields(node, df)
    assert (out["domain"] == "demography").all()
    assert (out["load_date"] == datetime.date.today()).all()
    assert (out["k"] == 7).all()
    assert out["dbl"].tolist() == [2, 4, 6, 8]
    assert "domain" not in df.columns  # no muta la entrada


def test_add_fields_errors(df):
    for expr in ("unknown_fn()", "no_such_col + 1"):
        node = AddFieldsTransformation(
            name="a",
            type="add_fields",
            input="x",
            config={"fields": [{"name": "z", "expression": expr}]},
        )
        with pytest.raises(TransformError):
            apply_add_fields(node, df)


def test_group(df):
    node = GroupTransformation(
        name="g",
        type="group",
        input="x",
        config={
            "group_fields": ["province"],
            "aggregations": [
                "sum(total) as total_population",
                "avg(total) as m",
                "count(total) as n",
                "min(total) as lo",
                "max(total) as hi",
            ],
        },
    )
    out = apply_group(node, df)
    a = out[out["province"] == "A"].iloc[0]
    assert (a["total_population"], a["m"], a["n"], a["lo"], a["hi"]) == (3, 1.5, 2, 1, 2)


def test_group_missing_column(df):
    node = GroupTransformation(
        name="g",
        type="group",
        input="x",
        config={"group_fields": ["nope"], "aggregations": ["sum(total) as t"]},
    )
    with pytest.raises(TransformError):
        apply_group(node, df)
