import pandas as pd

from mdf.config import GroupTransformation
from mdf.errors import TransformError
from mdf.expressions import parse_aggregation
from mdf.registry import transformation


@transformation("group")
def apply_group(node: GroupTransformation, df: pd.DataFrame) -> pd.DataFrame:
    named = {}
    for spec in node.config.aggregations:
        func, column, alias = parse_aggregation(spec)
        named[alias] = (column, func)
    try:
        return df.groupby(node.config.group_fields, as_index=False, dropna=False).agg(**named)
    except Exception as exc:
        raise TransformError(f"Error en group {node.name!r}: {exc}") from exc
