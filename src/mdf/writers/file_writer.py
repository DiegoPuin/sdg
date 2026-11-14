"""Writer `file` (Parquet como directorio de ficheros)."""

import uuid

import pandas as pd

from mdf.config import FileOutput
from mdf.context import RunContext
from mdf.errors import WriteError
from mdf.registry import writer


def _write_part(df: pd.DataFrame, fs, directory: str) -> None:
    fs.makedirs(directory, exist_ok=True)
    with fs.open(f"{directory}/part-{uuid.uuid4().hex}.parquet", "wb") as fh:
        df.to_parquet(fh, index=False)


@writer("file")
def write_file(node: FileOutput, df: pd.DataFrame, ctx: RunContext) -> dict:
    fs = ctx.storage.fs
    base = ctx.storage.path(node.config.path).rstrip("/")
    cfg = node.config
    try:
        if cfg.save_mode == "overwrite" and fs.exists(base):
            fs.rm(base, recursive=True)
        if cfg.partition:
            if cfg.partition not in df.columns:
                raise WriteError(f"La columna de partición {cfg.partition!r} no existe")
            for value, part in df.groupby(cfg.partition, dropna=False):
                _write_part(
                    part.drop(columns=[cfg.partition]), fs, f"{base}/{cfg.partition}={value}"
                )
        else:
            _write_part(df, fs, base)
    except WriteError:
        raise
    except Exception as exc:
        raise WriteError(f"No se pudo escribir {cfg.path!r}: {exc}") from exc
    return {}
