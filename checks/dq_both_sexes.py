"""Check B: calidad de datos (Both sexes == Men + Women).

Uso: python checks/dq_both_sexes.py --file PATH [--out DIR] [--tolerance 0]
"""

import argparse
import os
import sys

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from common import clean, read_csv, to_number  # type: ignore[no-redef]
else:
    from checks.common import clean, read_csv, to_number

SEXES = ["Both sexes", "Men", "Women"]
OUT_COLUMNS = ["province", "municipality", *SEXES, "delta", "issue_type"]


def analyze(df: pd.DataFrame, tolerance: int = 0) -> pd.DataFrame:
    rows: list[dict] = []
    for (province, municipality), group in df.groupby(["province", "municipality"], sort=True):
        values = dict(zip(group["sex"], group["total"], strict=True))
        base = {"province": province, "municipality": municipality}
        for s in SEXES:
            base[s] = clean(values.get(s, ""))

        def add(issue: str, delta: str = "", base=base) -> None:
            rows.append({**base, "delta": delta, "issue_type": issue})

        if any(s not in values for s in SEXES):
            add("INCOMPLETE_GROUP")
        present = {s: values[s] for s in SEXES if s in values}
        if any(v.strip() == "" for v in present.values()):
            add("NULL_VALUE")
        if any(v.strip() != "" and to_number(v) is None for v in present.values()):
            add("NON_NUMERIC")
        if len(present) == 3:
            nums = [to_number(present[s]) for s in SEXES]
            if all(n is not None for n in nums):
                delta = nums[0] - (nums[1] + nums[2])
                if abs(delta) > tolerance:
                    add("RULE_VIOLATION", f"{delta:+d}")
    return pd.DataFrame(rows, columns=OUT_COLUMNS)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    p.add_argument("--out", default="./out")
    p.add_argument("--tolerance", type=int, default=0)
    args = p.parse_args(argv)
    try:
        issues = analyze(read_csv(args.file), args.tolerance)
        os.makedirs(args.out, exist_ok=True)
        issues.to_csv(os.path.join(args.out, "dq_violations.csv"), index=False)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print("Resumen por categoría:")
    for cat in ("RULE_VIOLATION", "NULL_VALUE", "NON_NUMERIC", "INCOMPLETE_GROUP"):
        print(f"  {cat}: {int((issues['issue_type'] == cat).sum())}")
    if len(issues):
        print(issues.to_string(index=False))
    ok = issues.empty
    print("STATUS: OK" if ok else "STATUS: PENDING_REVIEW")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
