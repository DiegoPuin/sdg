import pytest

from mdf.config import parse_metadata
from mdf.errors import MetadataError

P = {"year": "2024"}


def flow(m):
    return m["dataflows"][0]


def test_real_metadata_valid(meta):
    assert parse_metadata(meta(), P).dataflows[0].name == "access-test"


def test_duplicate_names(meta):
    m = meta()
    flow(m)["outputs"][0]["name"] = "demo_data"
    with pytest.raises(MetadataError, match="duplicado"):
        parse_metadata(m, P)


def test_missing_input_reference(meta):
    m = meta()
    flow(m)["transformations"][0]["input"] = "nope"
    with pytest.raises(MetadataError, match="inexistente"):
        parse_metadata(m, P)


def test_missing_output_input_reference(meta):
    m = meta()
    flow(m)["outputs"][0]["input"] = "nope"
    with pytest.raises(MetadataError, match="inexistente"):
        parse_metadata(m, P)


def test_missing_waits_reference(meta):
    m = meta()
    flow(m)["inputs"][1]["waits"] = ["nope"]
    with pytest.raises(MetadataError, match="espera un output inexistente"):
        parse_metadata(m, P)


def test_cycle(meta):
    m = meta()
    flow(m)["transformations"][1]["input"] = "filter_rows"  # new_fields <- filter_rows
    with pytest.raises(MetadataError, match="ciclo"):
        parse_metadata(m, P)


def test_merge_without_primary_key(meta):
    m = meta()
    flow(m)["outputs"][2]["config"].pop("primary_key")
    with pytest.raises(MetadataError, match="primary_key"):
        parse_metadata(m, P)


def test_invalid_save_mode(meta):
    m = meta()
    flow(m)["outputs"][0]["config"]["save_mode"] = "merge"
    with pytest.raises(MetadataError):
        parse_metadata(m, P)


def test_unknown_types(meta):
    m = meta()
    flow(m)["transformations"][0]["type"] = "pivot"
    with pytest.raises(MetadataError):
        parse_metadata(m, P)
    m = meta()
    flow(m)["inputs"][0]["type"] = "kafka"
    with pytest.raises(MetadataError):
        parse_metadata(m, P)
    m = meta()
    flow(m)["inputs"][0]["config"]["format"] = "xml"
    with pytest.raises(MetadataError):
        parse_metadata(m, P)


def test_unsupported_reader_option(meta):
    m = meta()
    flow(m)["inputs"][0]["options"]["quote"] = "x"
    with pytest.raises(MetadataError, match="opciones no soportadas"):
        parse_metadata(m, P)


def test_unsupported_aggregation(meta):
    m = meta()
    flow(m)["transformations"][2]["config"]["aggregations"] = ["median(total) as m"]
    with pytest.raises(MetadataError):
        parse_metadata(m, P)


def test_missing_param(meta):
    with pytest.raises(MetadataError, match="year"):
        parse_metadata(meta(), {})


def test_param_rendered(meta):
    parsed = parse_metadata(meta(), P)
    assert parsed.dataflows[0].inputs[0].config.path == "/data/demo/input/data2024.csv"
