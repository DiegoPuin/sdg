import pandas as pd

from checks import diff_rows, dq_both_sexes


def write(path, rows):
    lines = ["province;municipality;sex;total"] + [";".join(r) for r in rows]
    path.write_bytes(("﻿" + "\r\n".join(lines) + "\r\n").encode("utf-8"))
    return str(path)


def test_diff_rows(tmp_path, capsys):
    old = write(
        tmp_path / "o.csv",
        [
            ["P1", "M1", "Men", "1.000"],
            ["P1", "M1", "Women", "5"],
            ["P1", "N/A", "Men", "7"],
            ["P1", "M2", "Men", "9"],
        ],
    )
    new = write(
        tmp_path / "n.csv",
        [
            ["P1", "M1", "Men", "1.001"],
            ["P1", "M1", "Women", "5"],
            ["P1", "N/A", "Men", "7"],
            ["P1", "M3", "Men", "4"],
        ],
    )
    out = tmp_path / "out"
    assert diff_rows.main(["--old", old, "--new", new, "--out", str(out)]) == 0
    assert "añadidas=1 eliminadas=1 cambiadas=1" in capsys.readouterr().out
    ch = pd.read_csv(out / "changed.csv", dtype=str)
    assert ch.iloc[0].tolist() == ["P1", "M1", "Men", "1000", "1001"]
    assert pd.read_csv(out / "added.csv", dtype=str)["municipality"].tolist() == ["M3"]
    assert pd.read_csv(out / "removed.csv", dtype=str)["municipality"].tolist() == ["M2"]


def test_diff_rows_non_numeric_and_errors(tmp_path, capsys):
    old = write(tmp_path / "o.csv", [["P", "M", "Men", "x"], ["P", "M", "Women", "x"]])
    new = write(tmp_path / "n.csv", [["P", "M", "Men", "x"], ["P", "M", "Women", "y"]])
    assert diff_rows.main(["--old", old, "--new", new, "--out", str(tmp_path / "o")]) == 0
    assert "cambiadas=1" in capsys.readouterr().out
    assert diff_rows.main(["--old", "nope.csv", "--new", new]) == 2
    bad = tmp_path / "bad.csv"
    bad.write_text("a;b\n1;2\n")
    assert diff_rows.main(["--old", str(bad), "--new", new]) == 2


def check(tmp_path, rows, *extra):
    f = write(tmp_path / "f.csv", rows)
    return dq_both_sexes.main(["--file", f, "--out", str(tmp_path / "o"), *extra])


def issues(tmp_path):
    return pd.read_csv(tmp_path / "o" / "dq_violations.csv", dtype=str, keep_default_na=False)


def test_dq_ok(tmp_path, capsys):
    rows = [
        ["P", "M", "Both sexes", "3"],
        ["P", "M", "Men", "1"],
        ["P", "M", "Women", "2"],
        ["P", "N/A", "Both sexes", "1.000"],
        ["P", "N/A", "Men", "400"],
        ["P", "N/A", "Women", "600"],
    ]
    assert check(tmp_path, rows) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "STATUS: OK"
    assert issues(tmp_path).empty


def test_dq_rule_violation_and_tolerance(tmp_path, capsys):
    rows = [["P", "M", "Both sexes", "12"], ["P", "M", "Men", "5"], ["P", "M", "Women", "9"]]
    assert check(tmp_path, rows) == 1
    out = capsys.readouterr().out
    assert out.strip().splitlines()[-1] == "STATUS: PENDING_REVIEW"
    i = issues(tmp_path)
    assert i.iloc[0]["issue_type"] == "RULE_VIOLATION" and i.iloc[0]["delta"] == "-2"
    assert check(tmp_path, rows, "--tolerance", "2") == 0


def test_dq_null_nonnumeric_incomplete(tmp_path):
    rows = [
        ["P", "A", "Both sexes", "3"],
        ["P", "A", "Men", ""],
        ["P", "A", "Women", "2"],
        ["P", "B", "Both sexes", "3"],
        ["P", "B", "Men", "x"],
        ["P", "B", "Women", "2"],
        ["P", "C", "Both sexes", "3"],
        ["P", "C", "Men", "1"],
    ]
    assert check(tmp_path, rows) == 1
    got = {(r.municipality, r.issue_type) for r in issues(tmp_path).itertuples()}
    assert got == {("A", "NULL_VALUE"), ("B", "NON_NUMERIC"), ("C", "INCOMPLETE_GROUP")}


def test_dq_errors(tmp_path):
    assert dq_both_sexes.main(["--file", str(tmp_path / "nope.csv")]) == 2
    bad = tmp_path / "bad.csv"
    bad.write_text("a;b\n1;2\n")
    assert dq_both_sexes.main(["--file", str(bad)]) == 2
