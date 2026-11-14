"""Renderizado de plantillas Jinja2 sobre todas las cadenas del metadata."""

from typing import Any

import jinja2

from mdf.errors import MetadataError

_ENV = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False)  # noqa: S701


def render_value(value: Any, params: dict[str, Any]) -> Any:
    if isinstance(value, str):
        try:
            return _ENV.from_string(value).render(**params)
        except jinja2.UndefinedError as exc:
            raise MetadataError(f"Parámetro no definido en plantilla {value!r}: {exc}") from exc
        except jinja2.TemplateError as exc:
            raise MetadataError(f"Plantilla inválida {value!r}: {exc}") from exc
    if isinstance(value, list):
        return [render_value(v, params) for v in value]
    if isinstance(value, dict):
        return {k: render_value(v, params) for k, v in value.items()}
    return value


def parse_params(items: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise MetadataError(f"Parámetro inválido {item!r}; se esperaba k=v")
        k, v = item.split("=", 1)
        out[k.strip()] = v
    return out
