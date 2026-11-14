import json
import os

import pandas as pd
import pytest

from mdf import cli
from mdf.errors import MetadataError, ReadError
from mdf.runner import Connections, run
from mdf.storage import Storage


def make_metadata(tmp_path, mutate=None):
    meta = {
        "dataflows": [
            {
                "name": "t",
                "inputs": [
                    {
                        "name": "src",
                        "type": "file",
                        "config": {"path": "/data/in/{{ year }}.csv", "format": "csv"},
                        "options": {"header": "true", "delimiter": ";", "thousands": "."},
                    }
                ],
                "transformations": [
                    {
                        "name": "f",
                        "type": "filter",
                        "input": "src",
                        "config": {"filter": "total > 1"},
                    }
                ],
                "outputs": [
                    {
                        "name": "w",
                        "type": "file",
                        "input": "f",
                        "config": {
                            "path": "/data/out",
                            "format": "parquet",
                            "save_mode": "overwrite",
                        },
                    }
                ],
            }
        ]
    }
    if mutate:
        mutate(meta)
    p = tmp_path / "meta.json"
    p.write_text(json.dumps(meta))
    return str(p)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "root"
    (r / "data" / "in").mkdir(parents=True)
    (r / "data" / "in" / "2024.csv").write_bytes(
        b"\xef\xbb\xbfa;total\r\nx;1\r\ny;2.000\r\nz;3\r\n"
    )
    return r


def test_run_end_to_end_local(tmp_path, root):
    storage = Storage(local_root=str(root))
    res = run(make_metadata(tmp_path), {"year": 2024}, Connections(), storage=storage)
    assert [n["node"] for n in res.nodes] == ["src", "f", "w"]
    assert res.nodes[-1]["rows"] == 2 and res.nodes[0]["rows"] == 3
    assert {"run_id", "dataflow", "node", "type", "rows", "duration_ms"} <= set(res.nodes[0])
    assert len(pd.read_parquet(root / "data" / "out")) == 2


def test_run_selected_and_unknown_dataflow(tmp_path, root):
    storage = Storage(local_root=str(root))
    path = make_metadata(tmp_path)
    run(path, {"year": 2024}, Connections(), dataflow="t", storage=storage)
    with pytest.raises(MetadataError):
        run(path, {"year": 2024}, Connections(), dataflow="nope", storage=storage)


def test_run_read_error(tmp_path, root):
    storage = Storage(local_root=str(root))
    with pytest.raises(ReadError):
        run(make_metadata(tmp_path), {"year": 1999}, Connections(), storage=storage)


def test_cli_exit_codes(tmp_path, root, monkeypatch):
    path = make_metadata(tmp_path)
    assert cli.main(["validate", "--metadata", path, "--param", "year=2024"]) == 0
    assert cli.main(["validate", "--metadata", path]) == 2
    assert cli.main(["validate", "--metadata", str(tmp_path / "nope.json")]) == 2
    assert cli.main(["validate", "--metadata", path, "--param", "bad"]) == 2
    # run sin S3 accesible -> error de lectura (3)
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("S3_ACCESS_KEY", "a")
    monkeypatch.setenv("S3_SECRET_KEY", "b")
    assert cli.main(["run", "--metadata", path, "--param", "year=2024"]) == 3


def test_cli_run_ok_and_transform_error(tmp_path, root, monkeypatch):
    import mdf.runner as runner

    real = runner.Storage
    monkeypatch.setattr(runner, "Storage", lambda c: real(local_root=str(root)))
    path = make_metadata(tmp_path)
    assert cli.main(["run", "--metadata", path, "--param", "year=2024"]) == 0
    assert os.path.isdir(root / "data" / "out")

    def bad(meta):
        meta["dataflows"][0]["transformations"][0]["config"]["filter"] = "zzz ==="

    assert (
        cli.main(["run", "--metadata", make_metadata(tmp_path, bad), "--param", "year=2024"]) == 4
    )
