"""Check A: filas que cambian entre dos CSV.

Uso: python checks/diff_rows.py --old PATH --new PATH [--out DIR]
"""

import argparse
import os
import sys

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from common import KEY, clean, read_csv, to_number  # type: ignore[no-redef]
else:
    from checks.common import KEY, clean, read_csv, to_number


def compare(old: pd.DataFrame, new: pd.DataFrame) -> dict[str, pd.DataFrame]:
    merged = old.merge(new, on=KEY, how="outer", suffixes=("_old", "_new"), indicator=True)
    added = merged[merged["_merge"] == "right_only"][[*KEY, "total_new"]]
    removed = merged[merged["_merge"] == "left_only"][[*KEY, "total_old"]]
    both = merged[merged["_merge"] == "both"].copy()
    old_n = both["total_old"].map(to_number)
    new_n = both["total_new"].map(to_number)
    # compara como entero; si alguno no es numérico, compara el texto
    same = [
        (o == n) if o is not None and n is not None else (so == sn)
        for o, n, so, sn in zip(old_n, new_n, both["total_old"], both["total_new"], strict=True)
    ]
    changed = both[[not s for s in same]][[*KEY, "total_old", "total_new"]]
    changed = changed.assign(
        total_old=changed["total_old"].map(clean), total_new=changed["total_new"].map(clean)
    )
    added = added.assign(total_new=added["total_new"].map(clean))
    removed = removed.assign(total_old=removed["total_old"].map(clean))
    return {
        "added": added.rename(columns={"total_new": "total"}).reset_index(drop=True),
        "removed": removed.rename(columns={"total_old": "total"}).reset_index(drop=True),
        "changed": changed.reset_index(drop=True),
    }


def run(old_path: str, new_path: str, out_dir: str) -> dict[str, pd.DataFrame]:
    result = compare(read_csv(old_path), read_csv(new_path))
    os.makedirs(out_dir, exist_ok=True)
    for name, frame in result.items():
        frame.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p.add_argument("--out", default="./out")
    args = p.parse_args(argv)
    try:
        result = run(args.old, args.new, args.out)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        f"Resumen: añadidas={len(result['added'])} eliminadas={len(result['removed'])} "
        f"cambiadas={len(result['changed'])}"
    )
    if len(result["changed"]):
        print(
            result["changed"]
            .rename(columns={"total_old": "anterior", "total_new": "nuevo"})
            .to_string(index=False)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
