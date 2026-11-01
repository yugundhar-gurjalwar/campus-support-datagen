"""Command line interface:  python -m campus_support <generate|validate|evaluate|repro-check|docs> ..."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

from . import __version__, evaluate as EV, schema, validate as V
from .config import DEFAULT_SEED, Config
from .io_export import export_all, load_ground_truth, load_tables, sha256
from .pipeline import generate
from .schema import FORBIDDEN_INPUT_COLUMNS, ISSUE_TYPES, TABLE_ORDER

SOURCE_MANIFEST = {
    "external_data_used": False,
    "sources": [],
    "statement": ("All records are synthetic and produced by this generator from a fixed seed. No external dataset, "
                  "scraped page, or personal data was used or redistributed; policy articles are authored by the "
                  "generator (catalog.py). Names are drawn from small fictional pools and e-mails use the reserved "
                  "example domain campus.example.edu."),
    "schema_inspiration": ["Generic public concepts of campus help-desk / ticketing workflows (no dataset retrieved)."],
    "retrieval_date": None, "license_terms": "Not applicable (no third-party data).",
    "transformations": "None (no external input).", "fields_discarded": "None (no external input).",
}


def _add_params(p):
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--tickets", type=int, default=5000)
    p.add_argument("--articles", type=int, default=200)
    p.add_argument("--messages-per-ticket", type=float, default=4.0, help="total messages = tickets x this (20,000 at defaults)")
    p.add_argument("--anomaly-rate", type=float, default=0.02, help="share of tickets per injected anomaly type")


def _cfg(a) -> Config:
    return Config(seed=a.seed, tickets=a.tickets, articles=a.articles, messages_per_ticket=a.messages_per_ticket,
                  anomaly_rate=a.anomaly_rate)


def _command(a) -> str:
    return (f"python -m campus_support generate --seed {a.seed} --tickets {a.tickets} --articles {a.articles} "
            f"--messages-per-ticket {a.messages_per_ticket} --anomaly-rate {a.anomaly_rate} --out <DIR>")


def _file_index(out: Path) -> dict:
    idx = {}
    for sub in ("csv", "json", "sql", "ground_truth"):
        for p in sorted((out / sub).iterdir()):
            rel = f"{sub}/{p.name}"
            idx[rel] = dict(bytes=p.stat().st_size, sha256=sha256(p))
    return idx


def _check_sql(out: Path, expected_rows: dict, rep: V.Report) -> None:
    con = sqlite3.connect(":memory:")
    bad = []
    try:
        con.executescript((out / "sql" / "schema.sql").read_text(encoding="utf-8"))
        con.executescript((out / "sql" / "seed.sql").read_text(encoding="utf-8"))
        for name in TABLE_ORDER:
            n = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            if n != expected_rows[name]:
                bad.append(f"{name}: sql {n} != csv {expected_rows[name]}")
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        bad += [f"fk violation {r}" for r in fk[:5]]
    except Exception as exc:  # noqa: BLE001
        bad.append(f"sql load failed: {exc}")
    rep.add("exports", "sql_seed_loads_in_sqlite_with_foreign_keys_enforced", bad, len(TABLE_ORDER))


def _check_no_leakage(tables: dict, out: Path, rep: V.Report) -> None:
    bad = []
    for name in TABLE_ORDER:
        cols = {c.name for c in schema.TABLE_MAP[name].cols}
        bad += [f"{name}.{c}" for c in cols & FORBIDDEN_INPUT_COLUMNS]
        header = (out / "csv" / f"{name}.csv").read_text(encoding="utf-8").split("\n", 1)[0].split(",")
        bad += [f"{name}.csv header {c}" for c in header if c in FORBIDDEN_INPUT_COLUMNS]
    tokens = set(ISSUE_TYPES) | {"ground_truth", "injected"}
    for m in tables["message"]:
        if any(tok in m["body"] for tok in tokens):
            bad.append(m["message_id"])
    for r in tables["ticket"]:
        if any(tok in r["subject"] for tok in tokens):
            bad.append(r["ticket_id"])
    rep.add("ground_truth", "ground_truth_never_present_in_input_tables", bad, len(TABLE_ORDER))


def build(cfg: Config, out: Path, command: str) -> tuple:
    out = Path(out)
    tables, ground = generate(cfg)
    export_all(out, tables, ground)
    loaded = load_tables(out)                        # validate what was actually written, not in-memory objects
    loaded_gt = load_ground_truth(out)
    expected = dict(ticket=cfg.tickets, knowledge_article=cfg.articles, message=cfg.messages)
    rep = V.validate(loaded, cfg.as_of, expected)
    _check_sql(out, {k: len(v) for k, v in loaded.items()}, rep)
    _check_no_leakage(loaded, out, rep)
    ev = EV.evaluate(loaded, loaded_gt, cfg.as_of)
    meta = out / "metadata"
    run_cfg = dict(generator_version=__version__, seed=cfg.seed, tickets=cfg.tickets, articles=cfg.articles,
                   messages=cfg.messages, policies=cfg.policies, anomaly_rate=cfg.anomaly_rate,
                   window_start=cfg.window_start.isoformat(), window_end=cfg.window_end.isoformat(),
                   as_of=cfg.as_of.isoformat(), command=command)
    (meta / "run_config.json").write_text(json.dumps(run_cfg, indent=1) + "\n", encoding="utf-8")
    (meta / "source_manifest.json").write_text(json.dumps(SOURCE_MANIFEST, indent=1) + "\n", encoding="utf-8")
    (meta / "validation_summary.json").write_text(json.dumps(rep.to_dict(), indent=1) + "\n", encoding="utf-8")
    (meta / "validation_summary.md").write_text(V.to_markdown(rep), encoding="utf-8")
    (meta / "evaluation_report.json").write_text(json.dumps(ev, indent=1) + "\n", encoding="utf-8")
    (meta / "evaluation_report.md").write_text(EV.to_markdown(ev), encoding="utf-8")
    manifest = dict(generator_version=__version__, seed=cfg.seed, command=command,
                    row_counts={k: len(v) for k, v in loaded.items()},
                    ground_truth_rows={k: len(v) for k, v in loaded_gt.items()}, files=_file_index(out))
    (meta / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return rep, ev, manifest


def _repro(cfg: Config, data_dir: Path | None) -> dict:
    runs = []
    with tempfile.TemporaryDirectory() as td:
        for i in (1, 2):
            tables, ground = generate(cfg)
            out = Path(td) / f"run{i}"
            export_all(out, tables, ground)
            runs.append(dict(row_counts={k: len(v) for k, v in tables.items()}, files=_file_index(out)))
    same = runs[0] == runs[1]
    mism = [] if same else [f for f in runs[0]["files"] if runs[0]["files"][f] != runs[1]["files"].get(f)]
    committed = None
    if data_dir and (Path(data_dir) / "metadata" / "manifest.json").exists():
        m = json.loads((Path(data_dir) / "metadata" / "manifest.json").read_text())
        committed = dict(matches_committed_data=all(m["files"].get(f) == v for f, v in runs[0]["files"].items()),
                         committed_files_compared=len(runs[0]["files"]))
    return dict(seed=cfg.seed, parameters=dict(tickets=cfg.tickets, articles=cfg.articles, messages=cfg.messages),
                run_1_equals_run_2=same, mismatched_files=mism, committed_dataset=committed,
                row_counts=runs[0]["row_counts"], files=runs[0]["files"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="campus_support", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="generate dataset + validation + evaluation reports")
    _add_params(g)
    g.add_argument("--out", required=True)
    v = sub.add_parser("validate", help="validate an exported dataset directory")
    v.add_argument("--data", required=True)
    e = sub.add_parser("evaluate", help="score detectors against ground truth for an exported dataset")
    e.add_argument("--data", required=True)
    r = sub.add_parser("repro-check", help="regenerate twice with the same seed and compare row counts / checksums")
    _add_params(r)
    r.add_argument("--data", help="optional committed dataset dir to compare against; report is written to its metadata/")
    d = sub.add_parser("docs", help="write DATA_DICTIONARY.md and ER_DIAGRAM.md")
    d.add_argument("--dir", default="docs")
    a = ap.parse_args(argv)

    if a.cmd == "generate":
        cfg = _cfg(a)
        rep, ev, man = build(cfg, Path(a.out), _command(a))
        print(f"generated {cfg.tickets} tickets / {cfg.articles} articles / {cfg.messages} messages -> {a.out}")
        d_ = rep.to_dict()
        print(f"validation: {'PASS' if d_['passed'] else 'FAIL'} ({d_['checks_total'] - d_['checks_failed']}/{d_['checks_total']} checks)")
        print("detection recall:", {k: v["recall"] for k, v in ev["detection"].items()})
        return 0 if rep.passed else 1
    if a.cmd in ("validate", "evaluate"):
        data = Path(a.data)
        cfgj = json.loads((data / "metadata" / "run_config.json").read_text())
        from datetime import datetime
        as_of = datetime.fromisoformat(cfgj["as_of"])
        tables = load_tables(data)
        if a.cmd == "validate":
            rep = V.validate(tables, as_of, dict(ticket=cfgj["tickets"], knowledge_article=cfgj["articles"], message=cfgj["messages"]))
            _check_sql(data, {k: len(v) for k, v in tables.items()}, rep)
            _check_no_leakage(tables, data, rep)
            print(V.to_markdown(rep))
            return 0 if rep.passed else 1
        print(EV.to_markdown(EV.evaluate(tables, load_ground_truth(data), as_of)))
        return 0
    if a.cmd == "repro-check":
        cfg = _cfg(a)
        rep = _repro(cfg, Path(a.data) if a.data else None)
        if a.data:
            (Path(a.data) / "metadata" / "reproducibility_report.json").write_text(json.dumps(rep, indent=1) + "\n")
        ok = rep["run_1_equals_run_2"] and (rep["committed_dataset"] is None or rep["committed_dataset"]["matches_committed_data"])
        print("reproducible:", ok, "| run1==run2:", rep["run_1_equals_run_2"], "| matches committed:", rep["committed_dataset"])
        return 0 if ok else 1
    if a.cmd == "docs":
        out = Path(a.dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "DATA_DICTIONARY.md").write_text(schema.dictionary_markdown(), encoding="utf-8")
        (out / "ER_DIAGRAM.md").write_text("# Entity-relationship diagram\n\n```mermaid\n" + schema.er_mermaid() + "```\n",
                                           encoding="utf-8")
        print(f"wrote docs to {out}/")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
