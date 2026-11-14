"""Utilidades compartidas por los checks (no importan mdf)."""

import pandas as pd

KEY = ["province", "municipality", "sex"]
COLUMNS = [*KEY, "total"]


def read_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en {path}: {missing}")
    return df[COLUMNS]


def to_number(value: str) -> int | None:
    """Convierte un total con separador de miles '.'; None si no es convertible."""
    try:
        return int(value.strip().replace(".", ""))
    except ValueError:
        return None


def clean(value: str) -> str:
    """Entero sin separador de miles si es numérico; si no, el texto original."""
    n = to_number(value)
    return str(n) if n is not None else value
