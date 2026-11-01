"""Step 9 exporters (CSV / JSON / SQL) and typed loaders. Output is byte-deterministic."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from .schema import TABLE_MAP, TABLE_ORDER, ddl

GT_COLUMNS = {
    "ground_truth_expected": ["ticket_id", "expected_team_id", "expected_priority", "expected_escalation",
                              "expected_escalation_reason", "expected_policy_id", "expected_article_id", "case_tags"],
    "ground_truth_anomalies": ["label_id", "ticket_id", "entity_type", "entity_id", "issue_type", "injected_field",
                               "original_value", "injected_value", "description"],
}
_GT_BOOL = {"expected_escalation"}


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _j(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    return v


def _lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + _s(v).replace("'", "''") + "'"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(path: Path, cols: list, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([_s(r.get(c)) for c in cols])


def write_json(path: Path, cols: list, rows: list) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("[\n" + ",\n".join(json.dumps({c: _j(r.get(c)) for c in cols}, ensure_ascii=False) for r in rows) + "\n]\n")


def export_all(out: Path, tables: dict, ground: dict) -> dict:
    """Writes csv/, json/, sql/, ground_truth/. Returns {relative_path: rows}."""
    for sub in ("csv", "json", "sql", "ground_truth", "metadata"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    counts = {}
    for name in TABLE_ORDER:
        cols = [c.name for c in TABLE_MAP[name].cols]
        write_csv(out / "csv" / f"{name}.csv", cols, tables[name])
        write_json(out / "json" / f"{name}.json", cols, tables[name])
        counts[f"csv/{name}.csv"] = len(tables[name])
    (out / "sql" / "schema.sql").write_text(ddl(), encoding="utf-8")
    with open(out / "sql" / "seed.sql", "w", encoding="utf-8", newline="\n") as f:
        f.write("-- Seed data. Load after schema.sql. Parents before children.\nPRAGMA foreign_keys = ON;\nBEGIN;\n")
        for name in TABLE_ORDER:
            cols = [c.name for c in TABLE_MAP[name].cols]
            head = f'INSERT INTO "{name}" (' + ", ".join(f'"{c}"' for c in cols) + ") VALUES\n"
            rows = tables[name]
            for i in range(0, len(rows), 500):
                chunk = rows[i:i + 500]
                f.write(head + ",\n".join("(" + ", ".join(_lit(r.get(c)) for c in cols) + ")" for r in chunk) + ";\n")
        f.write("COMMIT;\n")
    for name, cols in GT_COLUMNS.items():
        write_csv(out / "ground_truth" / f"{name}.csv", cols, ground[name])
        counts[f"ground_truth/{name}.csv"] = len(ground[name])
    with open(out / "ground_truth" / "ground_truth.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({k: [{c: _j(r.get(c)) for c in GT_COLUMNS[k]} for r in ground[k]] for k in GT_COLUMNS},
                  f, ensure_ascii=False, indent=1)
        f.write("\n")
    return counts


# ------------------------------------------------------------------ typed loading
def _parse(typ: str, v: str):
    if v == "":
        return None
    if typ == "int":
        return int(v)
    if typ == "float":
        return float(v)
    if typ == "bool":
        return v == "true"
    if typ == "date":
        return date.fromisoformat(v)
    if typ == "datetime":
        return datetime.fromisoformat(v)
    return v


def load_tables(data_dir: Path) -> dict:
    """Loads input tables (never ground truth) from csv/, converting to native types."""
    out = {}
    for name in TABLE_ORDER:
        types = {c.name: c.typ for c in TABLE_MAP[name].cols}
        with open(Path(data_dir) / "csv" / f"{name}.csv", newline="", encoding="utf-8") as f:
            out[name] = [{k: _parse(types[k], v) for k, v in row.items()} for row in csv.DictReader(f)]
    return out


def load_ground_truth(data_dir: Path) -> dict:
    out = {}
    for name, cols in GT_COLUMNS.items():
        with open(Path(data_dir) / "ground_truth" / f"{name}.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            for k in list(r):
                r[k] = (r[k] == "true") if k in _GT_BOOL else (r[k] if r[k] != "" else None)
        out[name] = rows
    return out
