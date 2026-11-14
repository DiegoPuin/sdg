import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def real_metadata() -> dict:
    return json.loads((ROOT / "metadata" / "metadata.json").read_text(encoding="utf-8"))


@pytest.fixture
def meta(real_metadata):
    return lambda: copy.deepcopy(real_metadata)
