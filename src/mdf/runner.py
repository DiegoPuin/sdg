"""Orquestación de la ejecución de un dataflow."""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from mdf import graph, registry
from mdf.config import Dataflow, load_metadata
from mdf.context import RunContext
from mdf.errors import MdfError, ReadError, TransformError, WriteError
from mdf.storage import Connections, Storage

__all__ = ["Connections", "RunResult", "run"]

log = logging.getLogger("mdf")


@dataclass
class RunResult:
    run_id: str
    nodes: list[dict[str, Any]] = field(default_factory=list)


def _emit(result: RunResult, record: dict[str, Any]) -> None:
    result.nodes.append(record)
    log.info(json.dumps(record, default=str))


def _run_dataflow(df: Dataflow, ctx: RunContext, result: RunResult) -> None:
    registry.load_builtin()
    nodes = {n.name: n for n in [*df.inputs, *df.transformations, *df.outputs]}
    kinds = graph.node_kinds(df)
    ctx.dataflow = df.name
    for name in graph.execution_order(df):
        node, kind = nodes[name], kinds[name]
        start = time.perf_counter()
        extra: dict[str, Any] = {}
        try:
            if kind == "input":
                frame = registry.READERS[node.type](node, ctx)
                ctx.results[name] = frame
            elif kind == "transformation":
                frame = registry.TRANSFORMATIONS[node.type](node, ctx.results[node.input])
                ctx.results[name] = frame
            else:
                frame = ctx.results[node.input]
                extra = registry.WRITERS[node.type](node, frame, ctx) or {}
        except MdfError:
            raise
        except Exception as exc:
            err = {"input": ReadError, "transformation": TransformError, "output": WriteError}[kind]
            raise err(f"Fallo en el nodo {name!r}: {exc}") from exc
        _emit(
            result,
            {
                "run_id": ctx.run_id,
                "dataflow": df.name,
                "node": name,
                "type": node.type,
                "rows": len(frame),
                "duration_ms": round((time.perf_counter() - start) * 1000),
                **extra,
            },
        )


def run(
    metadata_path: str,
    params: dict[str, Any],
    connections: Connections,
    dataflow: str | None = None,
    storage: Storage | None = None,
) -> RunResult:
    meta = load_metadata(metadata_path, params)
    flows = [d for d in meta.dataflows if dataflow in (None, d.name)]
    if not flows:
        from mdf.errors import MetadataError

        raise MetadataError(f"Dataflow no encontrado: {dataflow!r}")
    storage = storage or Storage(connections)
    ctx = RunContext(params=params, connections=connections, storage=storage)
    result = RunResult(run_id=ctx.run_id)
    for df in flows:
        ctx.results.clear()
        _run_dataflow(df, ctx, result)
    return result
