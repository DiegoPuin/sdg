"""Reader `file` (csv y parquet)."""

import pandas as pd
import pyarrow.parquet as pq

from mdf.config import FileInput
from mdf.context import RunContext
from mdf.errors import ReadError
from mdf.registry import reader


def csv_kwargs(options: dict[str, str]) -> dict:
    kwargs: dict = {}
    for key, value in options.items():
        if key == "header":
            kwargs["header"] = 0 if value.lower() == "true" else None
        elif key == "delimiter":
            kwargs["sep"] = value
        elif key == "thousands":
            kwargs["thousands"] = value
        else:
            raise ReadError(f"Opción no soportada: {key}")
    return kwargs


@reader("file")
def read_file(node: FileInput, ctx: RunContext) -> pd.DataFrame:
    path = ctx.storage.path(node.config.path)
    fs = ctx.storage.fs
    try:
        if node.config.format == "csv":
            with fs.open(path, "rb") as fh:
                return pd.read_csv(
                    fh,
                    encoding="utf-8-sig",
                    keep_default_na=False,
                    na_values=[""],
                    **csv_kwargs(node.options),
                )
        table = pq.read_table(path, filesystem=fs)
        return table.to_pandas()
    except ReadError:
        raise
    except Exception as exc:
        raise ReadError(f"No se pudo leer {node.config.path!r}: {exc}") from exc
