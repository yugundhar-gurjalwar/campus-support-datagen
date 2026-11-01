"""Validator negative tests (it must catch real defects), exporters, SQL load, CLI, reproducibility."""
import json
import sqlite3
from datetime import timedelta

import pytest

from campus_support.cli import main
from campus_support.config import Config
from campus_support.io_export import load_ground_truth, load_tables
from campus_support.schema import TABLE_ORDER, TRANSITIONS
from campus_support.validate import validate

AS_OF = Config().as_of


def failed(tables):
    rep = validate(tables, AS_OF)
    return {c["name"] for c in rep.checks if not c["passed"]}


def test_clean_data_has_no_failures(tables):
    assert failed(tables) == set()


def test_detects_broken_foreign_key(tables):
    tables["ticket"][0]["category_id"] = "CAT-FIN-99"
    assert "foreign_key" in failed(tables)


def test_detects_duplicate_primary_key(tables):
    tables["role"].append(dict(tables["role"][0]))
    assert "primary_key_unique" in failed(tables)


def test_detects_invalid_enum_and_missing_required(tables):
    tables["ticket"][3]["priority"] = "critical"
    tables["ticket"][4]["subject"] = None
    f = failed(tables)
    assert {"allowed_enum", "required_not_null"} <= f


def test_detects_bad_id_format(tables):
    tables["knowledge_article"][5]["article_id"] = "KB-5"
    assert "id_pattern" in failed(tables)


def test_detects_illegal_lifecycle_transition(tables):
    ev = next(e for e in tables["ticket_event"] if e["event_type"] == "routed")
    ev["to_status"] = "resolved"
    assert "lifecycle_transitions_and_sequences" in failed(tables)


def test_detects_status_not_matching_event_history(tables):
    tables["ticket"][10]["status"] = "new"
    assert "lifecycle_transitions_and_sequences" in failed(tables)


def test_detects_arithmetic_drift_in_derived_values(tables):
    tables["sla"][7]["first_response_due_at"] += timedelta(minutes=1)
    tables["ticket"][8]["message_count"] += 1
    assert "derived_values_reconcile_to_source_records" in failed(tables)


def test_detects_date_ordering_violation(tables):
    m = next(m for m in tables["message"] if m["message_seq"] == 2)
    m["sent_at"] -= timedelta(days=400)
    assert "date_ordering" in failed(tables)


def test_detects_article_version_gap(tables):
    a = next(a for a in tables["knowledge_article"] if a["version_no"] == 2)
    a["effective_from"] += timedelta(days=3)
    assert "article_version_chain_contiguous" in failed(tables)


def test_detects_assignee_outside_team_and_wrong_sender(tables):
    a = tables["assignment"][0]
    other = next(r for r in tables["requester"] if r["team_id"] and r["team_id"] != a["team_id"])
    a["assignee_id"] = other["requester_id"]
    assert "actor_role_term_assignment_joins" in failed(tables)


def test_detects_unrecorded_citation_version_and_duplicate_messages(tables):
    tables["message_citation"][0]["article_version_no"] += 1
    dup = dict(tables["message"][0], message_id="MSG-TKT-2026-000001-999", message_seq=999)
    tables["message"].append(dup)
    f = failed(tables)
    assert "citation_and_claim_integrity" in f and "no_duplicate_tickets_or_messages" in f


def test_every_transition_target_is_a_declared_status():
    from campus_support.schema import STATUSES
    assert set(TRANSITIONS.values()) <= set(STATUSES)


# ---------------------------------------------------------------- exports
@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    out = tmp_path_factory.mktemp("ds")
    rc = main(["generate", "--tickets", "150", "--articles", "32", "--out", str(out)])
    return out, rc


def test_cli_generate_passes_and_writes_all_artifacts(exported):
    out, rc = exported
    assert rc == 0
    for sub, names in {"csv": [f"{t}.csv" for t in TABLE_ORDER], "json": [f"{t}.json" for t in TABLE_ORDER],
                       "sql": ["schema.sql", "seed.sql"],
                       "ground_truth": ["ground_truth_expected.csv", "ground_truth_anomalies.csv", "ground_truth.json"],
                       "metadata": ["manifest.json", "run_config.json", "source_manifest.json", "validation_summary.md",
                                    "validation_summary.json", "evaluation_report.md", "evaluation_report.json"]}.items():
        for n in names:
            assert (out / sub / n).exists(), f"{sub}/{n}"
    assert json.loads((out / "metadata" / "validation_summary.json").read_text())["passed"] is True
    assert json.loads((out / "metadata" / "source_manifest.json").read_text())["external_data_used"] is False


def test_csv_round_trip_preserves_types_and_values(exported):
    out, _ = exported
    a = load_tables(out)
    b, _ = __import__("campus_support.pipeline", fromlist=["generate"]).generate(Config(tickets=150, articles=32))
    for name in TABLE_ORDER:
        assert a[name] == b[name], name


def test_json_export_matches_csv_row_counts(exported):
    out, _ = exported
    for name in ("ticket", "message", "sla", "message_citation"):
        n_json = len(json.loads((out / "json" / f"{name}.json").read_text()))
        assert n_json == len(load_tables(out)[name])


def test_sql_seed_loads_with_foreign_keys_enforced_and_supports_joins(exported):
    out, _ = exported
    con = sqlite3.connect(":memory:")
    con.executescript((out / "sql" / "schema.sql").read_text())
    con.executescript((out / "sql" / "seed.sql").read_text())
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    n_msg = con.execute("SELECT COUNT(*) FROM message").fetchone()[0]
    joined = con.execute("SELECT COUNT(*) FROM message m JOIN ticket t USING(ticket_id) "
                         "JOIN requester r ON r.requester_id = t.requester_id").fetchone()[0]
    assert n_msg == joined == 600
    with pytest.raises(sqlite3.IntegrityError):                       # DDL really enforces FKs
        con.execute("INSERT INTO ticket_event (event_id, ticket_id, event_seq, event_type, to_status, event_at, actor_type) "
                    "VALUES ('EVT-TKT-2026-999999-001','TKT-2026-999999',1,'created','new','2026-01-01T00:00:00','system')")


def test_ground_truth_files_load_and_are_not_in_csv_inputs(exported):
    out, _ = exported
    gt = load_ground_truth(out)
    assert len(gt["ground_truth_expected"]) == 150 and gt["ground_truth_anomalies"]
    for name in TABLE_ORDER:
        header = (out / "csv" / f"{name}.csv").read_text().split("\n", 1)[0]
        assert "issue_type" not in header and "expected_" not in header


def test_standalone_validate_and_evaluate_commands(exported, capsys):
    out, _ = exported
    assert main(["validate", "--data", str(out)]) == 0
    assert main(["evaluate", "--data", str(out)]) == 0
    assert "Anomaly detection" in capsys.readouterr().out


def test_validate_command_fails_on_tampered_export(exported, tmp_path):
    out, _ = exported
    import shutil
    bad = tmp_path / "bad"
    shutil.copytree(out, bad)
    p = bad / "csv" / "ticket.csv"
    p.write_text(p.read_text().replace("TKT-2026-000001,", "TKT-2026-000001,", 1).replace(",normal,", ",critical,", 1))
    assert main(["validate", "--data", str(bad)]) == 1


def test_reproducibility_two_runs_identical_and_match_manifest(exported):
    out, _ = exported
    assert main(["repro-check", "--tickets", "150", "--articles", "32", "--data", str(out)]) == 0
    rep = json.loads((out / "metadata" / "reproducibility_report.json").read_text())
    assert rep["run_1_equals_run_2"] and rep["committed_dataset"]["matches_committed_data"]
    assert rep["row_counts"]["ticket"] == 150
    # a different seed must NOT match the manifest -> the check is capable of failing
    assert main(["repro-check", "--tickets", "150", "--articles", "32", "--seed", "7", "--data", str(out)]) == 1


def test_docs_command(tmp_path):
    assert main(["docs", "--dir", str(tmp_path)]) == 0
    assert "## `ticket`" in (tmp_path / "DATA_DICTIONARY.md").read_text()
    assert "erDiagram" in (tmp_path / "ER_DIAGRAM.md").read_text()
