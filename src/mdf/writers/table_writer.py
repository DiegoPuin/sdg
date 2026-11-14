"""Writer `table` (Postgres). La generación de SQL es pura y se prueba sin base de datos."""

import pandas as pd
import psycopg

from mdf.config import TableOutput
from mdf.context import RunContext
from mdf.errors import WriteError
from mdf.registry import writer

STAGING = "_mdf_stage"


def qi(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def pg_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "bigint"
    if pd.api.types.is_float_dtype(series):
        return "double precision"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "timestamp"
    kind = pd.api.types.infer_dtype(series, skipna=True)
    if kind == "date":
        return "date"
    if kind == "datetime":
        return "timestamp"
    return "text"


def column_types(df: pd.DataFrame) -> dict[str, str]:
    return {c: pg_type(df[c]) for c in df.columns}


def create_table_sql(table: str, types: dict[str, str], primary_key: list[str] | None) -> str:
    cols = [f"{qi(c)} {t}" for c, t in types.items()]
    if primary_key:
        cols.append(f"PRIMARY KEY ({', '.join(qi(k) for k in primary_key)})")
    return f"CREATE TABLE IF NOT EXISTS {qi(table)} ({', '.join(cols)})"


def create_staging_sql(table: str) -> str:
    return f"CREATE TEMP TABLE {qi(STAGING)} (LIKE {qi(table)}) ON COMMIT DROP"


def copy_sql(columns: list[str]) -> str:
    return f"COPY {qi(STAGING)} ({', '.join(qi(c) for c in columns)}) FROM STDIN"


def append_sql(table: str, columns: list[str]) -> str:
    cols = ", ".join(qi(c) for c in columns)
    return f"INSERT INTO {qi(table)} ({cols}) SELECT {cols} FROM {qi(STAGING)}"


def truncate_sql(table: str) -> str:
    return f"TRUNCATE {qi(table)}"


def merge_counts_sql(table: str, columns: list[str], primary_key: list[str]) -> str:
    """Una fila: (inserted, updated, unchanged)."""
    non_key = [c for c in columns if c not in primary_key]
    join = " AND ".join(f"t.{qi(k)} = s.{qi(k)}" for k in primary_key)
    first_key = qi(primary_key[0])
    if non_key:
        t_cols = ", ".join(f"t.{qi(c)}" for c in non_key)
        s_cols = ", ".join(f"s.{qi(c)}" for c in non_key)
        differs = f"({t_cols}) IS DISTINCT FROM ({s_cols})"
    else:
        differs = "FALSE"
    return (
        "SELECT "
        f"count(*) FILTER (WHERE t.{first_key} IS NULL), "
        f"count(*) FILTER (WHERE t.{first_key} IS NOT NULL AND {differs}), "
        f"count(*) FILTER (WHERE t.{first_key} IS NOT NULL AND NOT ({differs})) "
        f"FROM {qi(STAGING)} s LEFT JOIN {qi(table)} t ON {join}"
    )


def merge_sql(table: str, columns: list[str], primary_key: list[str]) -> str:
    cols = ", ".join(qi(c) for c in columns)
    pk = ", ".join(qi(k) for k in primary_key)
    non_key = [c for c in columns if c not in primary_key]
    base = f"INSERT INTO {qi(table)} ({cols}) SELECT {cols} FROM {qi(STAGING)} ON CONFLICT ({pk}) "
    if not non_key:
        return base + "DO NOTHING"
    sets = ", ".join(f"{qi(c)} = EXCLUDED.{qi(c)}" for c in non_key)
    t_cols = ", ".join(f"{qi(table)}.{qi(c)}" for c in non_key)
    e_cols = ", ".join(f"EXCLUDED.{qi(c)}" for c in non_key)
    return base + f"DO UPDATE SET {sets} WHERE ({t_cols}) IS DISTINCT FROM ({e_cols})"


def validate_unique_key(df: pd.DataFrame, primary_key: list[str]) -> None:
    missing = [k for k in primary_key if k not in df.columns]
    if missing:
        raise WriteError(f"primary_key referencia columnas inexistentes: {missing}")
    dup = df.duplicated(subset=primary_key, keep=False)
    if dup.any():
        sample = df.loc[dup, primary_key].head(3).to_dict("records")
        raise WriteError(
            f"primary_key {primary_key} no es única en los datos ({int(dup.sum())} filas "
            f"afectadas); ejemplo: {sample}"
        )


def _rows(df: pd.DataFrame) -> list[tuple]:
    clean = df.astype(object).where(df.notna(), None)
    return list(clean.itertuples(index=False, name=None))


def _has_unique_constraint(cur, table: str, primary_key: list[str]) -> bool:  # pragma: no cover
    cur.execute(
        """
        SELECT array_agg(a.attname::text ORDER BY a.attname)
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
        WHERE i.indrelid = %s::regclass AND i.indisunique
        GROUP BY i.indexrelid
        """,
        (qi(table),),
    )
    wanted = sorted(primary_key)
    return any(sorted(row[0]) == wanted for row in cur.fetchall())


def _execute(df: pd.DataFrame, cfg, dsn: str) -> dict:  # pragma: no cover
    columns = list(df.columns)
    mode = cfg.save_mode
    pk = cfg.primary_key if mode == "merge" else None
    stats: dict = {}
    with psycopg.connect(dsn) as conn:  # una transacción; ROLLBACK ante excepción
        with conn.cursor() as cur:
            cur.execute(create_table_sql(cfg.table, column_types(df), pk))
            if mode == "merge" and not _has_unique_constraint(cur, cfg.table, cfg.primary_key):
                raise WriteError(
                    f"La tabla {cfg.table!r} no tiene restricción única sobre {cfg.primary_key}"
                )
            cur.execute(create_staging_sql(cfg.table))
            with cur.copy(copy_sql(columns)) as copy:
                for row in _rows(df):
                    copy.write_row(row)
            if mode == "append":
                cur.execute(append_sql(cfg.table, columns))
            elif mode == "overwrite":
                cur.execute(truncate_sql(cfg.table))
                cur.execute(append_sql(cfg.table, columns))
            else:
                cur.execute(merge_counts_sql(cfg.table, columns, cfg.primary_key))
                ins, upd, unch = cur.fetchone()
                stats = {"rows_inserted": ins, "rows_updated": upd, "rows_unchanged": unch}
                cur.execute(merge_sql(cfg.table, columns, cfg.primary_key))
    return stats


@writer("table")
def write_table(node: TableOutput, df: pd.DataFrame, ctx: RunContext) -> dict:
    cfg = node.config
    if cfg.save_mode == "merge":
        validate_unique_key(df, cfg.primary_key)
    if not ctx.connections.warehouse_dsn:
        raise WriteError("WAREHOUSE_DSN no está configurado")
    try:
        return _execute(df, cfg, ctx.connections.warehouse_dsn)
    except WriteError:
        raise
    except Exception as exc:
        raise WriteError(f"No se pudo escribir la tabla {cfg.table!r}: {exc}") from exc
