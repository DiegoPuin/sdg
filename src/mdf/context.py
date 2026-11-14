"""Contexto de una ejecución."""

import uuid
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from mdf.storage import Connections, Storage


@dataclass
class RunContext:
    params: dict[str, Any]
    connections: Connections
    storage: Storage
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    dataflow: str = ""
    results: dict[str, pd.DataFrame] = field(default_factory=dict)
