"""Grafo de ejecución del dataflow."""

from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING

from mdf.errors import MetadataError

if TYPE_CHECKING:
    from mdf.config import Dataflow


def node_kinds(df: "Dataflow") -> dict[str, str]:
    kinds: dict[str, str] = {}
    for kind, nodes in (
        ("input", df.inputs),
        ("transformation", df.transformations),
        ("output", df.outputs),
    ):
        for n in nodes:
            if n.name in kinds:
                raise MetadataError(f"Nombre de nodo duplicado: {n.name!r}")
            kinds[n.name] = kind
    return kinds


def dependencies(df: "Dataflow") -> dict[str, list[str]]:
    """nodo -> nodos de los que depende (input y waits)."""
    kinds = node_kinds(df)
    deps: dict[str, list[str]] = {name: [] for name in kinds}
    for n in df.transformations + df.outputs:
        if n.input not in kinds:
            raise MetadataError(f"El nodo {n.name!r} referencia un input inexistente: {n.input!r}")
        deps[n.name].append(n.input)
    output_names = {o.name for o in df.outputs}
    for i in df.inputs:
        for w in i.waits:
            if w not in output_names:
                raise MetadataError(f"El input {i.name!r} espera un output inexistente: {w!r}")
            deps[i.name].append(w)
    return deps


def execution_order(df: "Dataflow") -> list[str]:
    """Orden topológico determinista (desempata por orden de definición)."""
    deps = dependencies(df)
    position = {name: idx for idx, name in enumerate(deps)}
    sorter = TopologicalSorter(deps)
    try:
        sorter.prepare()
    except CycleError as exc:
        raise MetadataError(f"El dataflow {df.name!r} contiene un ciclo: {exc.args[1]}") from exc
    order: list[str] = []
    while sorter.is_active():
        for name in sorted(sorter.get_ready(), key=position.__getitem__):
            order.append(name)
            sorter.done(name)
    return order
