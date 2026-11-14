"""Resolución de rutas del metadata y acceso a ficheros vía fsspec."""

import os
from dataclasses import dataclass

import fsspec


@dataclass
class Connections:
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    warehouse_dsn: str = ""

    @classmethod
    def from_env(cls) -> "Connections":
        return cls(
            s3_endpoint_url=os.environ.get("S3_ENDPOINT_URL", ""),
            s3_access_key=os.environ.get("S3_ACCESS_KEY", ""),
            s3_secret_key=os.environ.get("S3_SECRET_KEY", ""),
            warehouse_dsn=os.environ.get("WAREHOUSE_DSN", ""),
        )


def to_uri(path: str) -> str:
    """`/<bucket>/<clave>` -> `s3://<bucket>/<clave>`."""
    return "s3://" + path.lstrip("/")


class Storage:
    """Modo `s3` (por defecto) o `local` (raíz configurable, para tests)."""

    def __init__(self, connections: Connections | None = None, local_root: str | None = None):
        self.local_root = local_root
        if local_root is not None:
            self.fs = fsspec.filesystem("file")
        else:
            c = connections or Connections()
            self.fs = fsspec.filesystem(
                "s3",
                key=c.s3_access_key or None,
                secret=c.s3_secret_key or None,
                client_kwargs={"endpoint_url": c.s3_endpoint_url or None},
                config_kwargs={"s3": {"addressing_style": "path"}},
            )

    def path(self, metadata_path: str) -> str:
        """Ruta dentro del filesystem (sin esquema)."""
        if self.local_root is not None:
            return os.path.join(self.local_root, metadata_path.lstrip("/"))
        return to_uri(metadata_path).removeprefix("s3://")
