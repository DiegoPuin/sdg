"""Modelos pydantic del metadata y su validación."""

import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from mdf import graph
from mdf.errors import MetadataError
from mdf.params import render_value

SUPPORTED_READER_OPTIONS = {"header", "delimiter", "thousands"}
AGG_RE = re.compile(r"^\s*(\w+)\(\s*(\w+)\s*\)\s+as\s+(\w+)\s*$")
AGG_FUNCS = {"sum", "count", "min", "max", "avg"}


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- inputs ---------------------------------------------------------------
class FileInputConfig(_Base):
    path: str
    format: Literal["csv", "parquet"]


class FileInput(_Base):
    name: str
    type: Literal["file"]
    config: FileInputConfig
    options: dict[str, str] = Field(default_factory=dict)
    waits: list[str] = Field(default_factory=list)

    @field_validator("options")
    @classmethod
    def _options(cls, v: dict[str, str]) -> dict[str, str]:
        bad = set(v) - SUPPORTED_READER_OPTIONS
        if bad:
            raise ValueError(f"opciones no soportadas: {sorted(bad)}")
        return v


# --- transformations ------------------------------------------------------
class FilterConfig(_Base):
    filter: str


class FilterTransformation(_Base):
    name: str
    type: Literal["filter"]
    input: str
    config: FilterConfig


class Field_(_Base):
    name: str
    expression: str


class AddFieldsConfig(_Base):
    fields: list[Field_]


class AddFieldsTransformation(_Base):
    name: str
    type: Literal["add_fields"]
    input: str
    config: AddFieldsConfig


class GroupConfig(_Base):
    group_fields: list[str]
    aggregations: list[str]

    @field_validator("aggregations")
    @classmethod
    def _aggs(cls, v: list[str]) -> list[str]:
        for a in v:
            m = AGG_RE.match(a)
            if not m or m.group(1).lower() not in AGG_FUNCS:
                raise ValueError(f"agregación no soportada: {a!r}")
        return v


class GroupTransformation(_Base):
    name: str
    type: Literal["group"]
    input: str
    config: GroupConfig


Transformation = Annotated[
    FilterTransformation | AddFieldsTransformation | GroupTransformation,
    Field(discriminator="type"),
]


# --- outputs --------------------------------------------------------------
class FileOutputConfig(_Base):
    path: str
    format: Literal["parquet"]
    save_mode: Literal["overwrite", "append"]
    partition: str | None = None


class FileOutput(_Base):
    name: str
    type: Literal["file"]
    input: str
    config: FileOutputConfig


class TableOutputConfig(_Base):
    table: str
    save_mode: Literal["merge", "append", "overwrite"]
    primary_key: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _pk(self) -> "TableOutputConfig":
        if self.save_mode == "merge" and not self.primary_key:
            raise ValueError("save_mode 'merge' requiere primary_key")
        return self


class TableOutput(_Base):
    name: str
    type: Literal["table"]
    input: str
    config: TableOutputConfig


Output = Annotated[FileOutput | TableOutput, Field(discriminator="type")]


class Dataflow(_Base):
    name: str
    inputs: list[FileInput]
    transformations: list[Transformation] = Field(default_factory=list)
    outputs: list[Output]

    @model_validator(mode="after")
    def _graph(self) -> "Dataflow":
        graph.execution_order(self)  # nombres únicos, referencias y ciclos
        return self


class Metadata(_Base):
    dataflows: list[Dataflow]


def _format_errors(exc: ValidationError) -> str:
    lines = []
    for e in exc.errors():
        loc = ".".join(str(p) for p in e["loc"])
        lines.append(f"  - {loc}: {e['msg']}")
    return "\n".join(lines)


def parse_metadata(raw: dict[str, Any], params: dict[str, Any]) -> Metadata:
    rendered = render_value(raw, params)
    try:
        return Metadata.model_validate(rendered)
    except ValidationError as exc:
        raise MetadataError(f"Metadata inválido:\n{_format_errors(exc)}") from exc


def load_metadata(path: str, params: dict[str, Any]) -> Metadata:
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise MetadataError(f"No se puede leer el metadata {path!r}: {exc}") from exc
    return parse_metadata(raw, params)
