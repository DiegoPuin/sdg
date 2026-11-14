"""Registros extensibles de lectores, transformaciones y escritores."""

from collections.abc import Callable

READERS: dict[str, Callable] = {}
TRANSFORMATIONS: dict[str, Callable] = {}
WRITERS: dict[str, Callable] = {}


def _register(table: dict[str, Callable], name: str):
    def deco(fn: Callable) -> Callable:
        table[name] = fn
        return fn

    return deco


def reader(name: str):
    return _register(READERS, name)


def transformation(name: str):
    return _register(TRANSFORMATIONS, name)


def writer(name: str):
    return _register(WRITERS, name)


def load_builtin() -> None:
    """Importa los módulos que registran los tipos incluidos."""
    from mdf.readers import file_reader  # noqa: F401
    from mdf.transformations import add_fields, filter, group  # noqa: F401
    from mdf.writers import file_writer, table_writer  # noqa: F401
