import pytest

from mdf import params
from mdf.config import parse_metadata
from mdf.errors import MetadataError
from mdf.graph import execution_order
from mdf.storage import Connections, Storage, to_uri


def test_topological_order(meta):
    order = execution_order(parse_metadata(meta(), {"year": "2024"}).dataflows[0])
    pos = order.index
    assert pos("demo_data") < pos("new_fields") < pos("filter_rows") < pos("write_last_file")
    assert pos("write_last_file") < pos("parquet_data") < pos("group_by_fields")
    assert pos("group_by_fields") < pos("write_delta_merge")
    assert pos("group_by_fields") < pos("write_delta_raw")


def test_render_and_strict_undefined():
    assert params.render_value({"a": ["x{{ year }}"]}, {"year": 2025}) == {"a": ["x2025"]}
    with pytest.raises(MetadataError):
        params.render_value("{{ missing }}", {})
    with pytest.raises(MetadataError):
        params.render_value("{{ unclosed", {})


def test_parse_params():
    assert params.parse_params(["year=2024", "a=b=c"]) == {"year": "2024", "a": "b=c"}
    assert params.parse_params(None) == {}
    with pytest.raises(MetadataError):
        params.parse_params(["bad"])


def test_to_uri():
    assert to_uri("/data/demo/input/data2024.csv") == "s3://data/demo/input/data2024.csv"


def test_local_storage_path(tmp_path):
    s = Storage(local_root=str(tmp_path))
    assert s.path("/data/x") == str(tmp_path / "data" / "x")


def test_s3_storage_path():
    s = Storage(Connections("http://localhost:9", "k", "s"))
    assert s.path("/data/demo/a.csv") == "data/demo/a.csv"


def test_connections_from_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://x")
    monkeypatch.setenv("WAREHOUSE_DSN", "dsn")
    c = Connections.from_env()
    assert c.s3_endpoint_url == "http://x" and c.warehouse_dsn == "dsn"
