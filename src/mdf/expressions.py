"""Expresiones de add_fields, agregaciones de group y funciones registradas."""

import datetime
import re
from collections.abc import Callable
from typing import Any

import pandas as pd

from mdf.config import AGG_RE
from mdf.errors import TransformError

FUNCTIONS: dict[str, Callable[[], Any]] = {
    "current_date": datetime.date.today,
    "current_timestamp": datetime.datetime.now,
}

_STR_LITERAL = re.compile(r"""^\s*(?:'(.*)'|"(.*)")\s*$""", re.S)
_CALL = re.compile(r"^\s*(\w+)\(\s*\)\s*$")
_NUMBER = re.compile(r"^\s*-?\d+(\.\d+)?\s*$")


def evaluate_field(df: pd.DataFrame, expression: str) -> Any:
    """Devuelve un escalar (columna constante) o una Serie."""
    m = _STR_LITERAL.match(expression)
    if m:
        return m.group(1) if m.group(1) is not None else m.group(2)
    if _NUMBER.match(expression):
        return float(expression) if "." in expression else int(expression)
    m = _CALL.match(expression)
    if m:
        name = m.group(1)
        if name not in FUNCTIONS:
            raise TransformError(f"Función no registrada: {name}()")
        return FUNCTIONS[name]()
    try:
        return df.eval(expression)
    except Exception as exc:
        raise TransformError(f"Expresión inválida {expression!r}: {exc}") from exc


def parse_aggregation(spec: str) -> tuple[str, str, str]:
    m = AGG_RE.match(spec)
    if not m:
        raise TransformError(f"Agregación no soportada: {spec!r}")
    func, column, alias = m.groups()
    func = func.lower()
    return ("mean" if func == "avg" else func), column, alias
