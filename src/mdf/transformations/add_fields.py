import pandas as pd

from mdf.config import AddFieldsTransformation
from mdf.expressions import evaluate_field
from mdf.registry import transformation


@transformation("add_fields")
def apply_add_fields(node: AddFieldsTransformation, df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for field in node.config.fields:
        out[field.name] = evaluate_field(out, field.expression)
    return out
