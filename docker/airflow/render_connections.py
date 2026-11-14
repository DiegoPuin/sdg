"""Renderiza connections/*.json expandiendo variables de entorno."""

import glob
import json
import os
import sys


def render(conn_dir: str) -> dict:
    merged: dict = {}
    for path in sorted(glob.glob(os.path.join(conn_dir, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            merged.update(json.loads(os.path.expandvars(fh.read())))
    return merged


def main() -> int:
    conn_dir = sys.argv[1] if len(sys.argv) > 1 else "/opt/airflow/connections"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/connections.json"  # noqa: S108
    data = render(conn_dir)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.chmod(out, 0o600)
    print(f"Conexiones renderizadas: {', '.join(data)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
