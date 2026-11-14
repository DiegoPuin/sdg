import pandas as pd

from mdf.config import FilterTransformation
from mdf.errors import TransformError
from mdf.registry import transformation


@transformation("filter")
def apply_filter(node: FilterTransformation, df: pd.DataFrame) -> pd.DataFrame:
    try:
        return df.query(node.config.filter).reset_index(drop=True)
    except Exception as exc:
        raise TransformError(f"Filtro inválido {node.config.filter!r}: {exc}") from exc
