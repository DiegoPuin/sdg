"""CLI: mdf run | mdf validate."""

import argparse
import logging
import sys

from mdf.config import load_metadata
from mdf.errors import MdfError
from mdf.params import parse_params
from mdf.runner import Connections, run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mdf")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="ejecuta el metadata")
    r.add_argument("--metadata", required=True)
    r.add_argument("--dataflow")
    r.add_argument("--param", action="append", default=[], metavar="k=v")
    v = sub.add_parser("validate", help="valida el metadata")
    v.add_argument("--metadata", required=True)
    v.add_argument("--param", action="append", default=[], metavar="k=v")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    try:
        params = parse_params(args.param)
        if args.command == "validate":
            meta = load_metadata(args.metadata, params)
            print(f"Metadata válido: {len(meta.dataflows)} dataflow(s)")
        else:
            run(args.metadata, params, Connections.from_env(), args.dataflow)
    except MdfError as exc:
        print(f"ERROR ({type(exc).__name__}): {exc}", file=sys.stderr)
        return exc.exit_code
    return 0


if __name__ == "__main__":
    sys.exit(main())
