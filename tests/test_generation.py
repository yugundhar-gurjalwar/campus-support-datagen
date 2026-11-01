"""Generation invariants: volumes, IDs, determinism, workflow rules, injected anomalies, ground truth."""
import re
from collections import Counter, defaultdict

import pytest

from campus_support.config import Config
from campus_support.evaluate import evaluate, run_detectors
from campus_support.pipeline import generate
from campus_support.schema import FORBIDDEN_INPUT_COLUMNS, ISSUE_TYPES, TABLE_MAP, TABLE_ORDER
from campus_support.validate import validate


def test_exact_volumes_and_all_tables_present(data, cfg):
    t, _ = data
    assert list(t) == TABLE_ORDER
    assert len(t["ticket"]) == cfg.tickets == 800
    assert len(t["knowledge_article"]) == cfg.articles == 120
    assert len(t["message"]) == cfg.messages == 3200
    assert len(t["retrieval_result"]) == len(t["sla"]) == cfg.tickets


def test_id_conventions(data):
    t, _ = data
    assert t["ticket"][0]["ticket_id"] == "TKT-2026-000001"
    assert t["knowledge_article"][0]["article_id"] == "KB-000001"
    assert t["policy_document"][0]["policy_id"] == "POL-FIN-2026-001"
    tid = t["ticket"][41]["ticket_id"]
    assert tid == "TKT-2026-000042"
    assert f"SLA-{tid}" in {s["sla_id"] for s in t["sla"]}
    assert f"MSG-{tid}-001" in {m["message_id"] for m in t["message"]}
    for tb in TABLE_ORDER:
        pat = next(c.pattern for c in TABLE_MAP[tb].cols if c.name == TABLE_MAP[tb].pk)
        assert all(re.search(pat, r[TABLE_MAP[tb].pk]) for r in t[tb])


def test_structural_validation_passes(data, cfg):
    rep = validate(data[0], cfg.as_of, dict(ticket=800, knowledge_article=120, message=3200))
    assert rep.passed, [c for c in rep.checks if not c["passed"]]


def test_same_seed_is_bit_identical_and_other_seed_differs():
    a, ga = generate(Config(tickets=60, articles=24))
    b, gb = generate(Config(tickets=60, articles=24))
    assert a == b and ga == gb
    c, _ = generate(Config(tickets=60, articles=24, seed=1))
    assert c["ticket"] != a["ticket"] and len(c["message"]) == len(a["message"])


def test_parameterised_scale_uses_same_generator():
    t, _ = generate(Config(tickets=150, articles=32, messages_per_ticket=4.5))
    assert (len(t["ticket"]), len(t["knowledge_article"]), len(t["message"])) == (150, 32, 675)


# ---------------------------------------------------------------- workflow / business rules on CLEAN tickets
def _clean(data):
    t, g = data
    flagged = {a["ticket_id"] for a in g["ground_truth_anomalies"]}
    return t, g, flagged


def test_clean_answers_cite_current_version_and_record_it(data, ctx):
    t, g, flagged = _clean(data)
    msgs = {m["message_id"]: m for m in t["message"]}
    n = 0
    for c in t["message_citation"]:
        m = msgs[c["message_id"]]
        if m["ticket_id"] in flagged:
            continue
        a = ctx.articles[c["article_id"]]
        d = m["sent_at"].date()
        assert a["effective_from"] <= d and (a["effective_to"] is None or d <= a["effective_to"])
        assert c["article_version_no"] == a["version_no"]
        n += 1
    assert n > 500
    for m in t["message"]:
        if m["message_type"] == "answer" and m["ticket_id"] not in flagged:
            assert any(c["message_id"] == m["message_id"] for c in t["message_citation"])


def test_clean_routing_matches_rule_and_authorization(data, ctx):
    t, g, flagged = _clean(data)
    tk = {r["ticket_id"]: r for r in t["ticket"]}
    for a in t["assignment"]:
        if a["ticket_id"] in flagged:
            continue
        r = tk[a["ticket_id"]]
        assert ctx.is_authorized(a["team_id"], r["category_id"], a["assigned_at"].date())
        if a["assignment_type"] == "initial":
            rule = ctx.route(r["category_id"], ctx.requesters[r["requester_id"]]["role_id"], r["created_at"].date())
            assert (a["team_id"], a["routing_rule_id"]) == (rule["target_team_id"], rule["routing_rule_id"])


def test_escalation_happens_iff_documented_trigger(data, ctx):
    t, g, flagged = _clean(data)
    esc = {e["ticket_id"]: e["reason_code"] for e in t["ticket_event"] if e["event_type"] == "escalated"}
    exp = {e["ticket_id"]: e for e in g["ground_truth_expected"]}
    tk = {r["ticket_id"]: r for r in t["ticket"]}
    for r in t["retrieval_result"]:
        tid = r["ticket_id"]
        if tid in flagged:
            continue
        x = tk[tid]
        dl = None if x["requester_deadline_at"] is None else (x["requester_deadline_at"] - x["created_at"]).total_seconds() / 3600
        reasons = ctx.escalation_reasons(x["category_id"], r["outcome"], dl)
        assert (tid in esc) == bool(reasons) == exp[tid]["expected_escalation"]
        if reasons:
            assert esc[tid] == reasons[0] == exp[tid]["expected_escalation_reason"]


def test_ambiguous_tickets_get_clarification_then_escalate_when_unresolved(data):
    t, _ = data
    kinds = defaultdict(list)
    for m in t["message"]:
        kinds[m["ticket_id"]].append(m["message_type"])
    esc = {e["ticket_id"] for e in t["ticket_event"] if e["event_type"] == "escalated"}
    for r in t["retrieval_result"]:
        tid = r["ticket_id"]
        if r["outcome"] == "low_confidence":
            assert kinds[tid].count("clarification_request") == 2          # max two rounds, then give up
        if r["initial_confidence"] < 0.70 and r["outcome"] == "matched":
            assert kinds[tid].count("clarification_request") == 1
    assert any(r["outcome"] == "low_confidence" and r["ticket_id"] in esc for r in t["retrieval_result"])


def test_history_is_append_only_state_is_derived_from_events(data):
    t, _ = data
    last = {}
    for e in sorted(t["ticket_event"], key=lambda e: (e["ticket_id"], e["event_seq"])):
        last[e["ticket_id"]] = e["to_status"]
    assert all(r["status"] == last[r["ticket_id"]] for r in t["ticket"])
    assert Counter(r["status"] for r in t["ticket"]).keys() >= {"closed", "resolved"}


def test_distribution_and_coverage(data):
    t, g = data
    assert len({r["category_id"] for r in t["ticket"]}) == 16
    assert {"portal", "email", "chat", "phone"} == {r["channel"] for r in t["ticket"]}
    assert {"low", "normal", "high", "urgent"} == {r["priority"] for r in t["ticket"]}
    tags = Counter(tag for e in g["ground_truth_expected"] for tag in (e["case_tags"] or "").split("|") if tag)
    for needed in ("ambiguous", "outdated_or_withdrawn_policy", "urgent_deadline", "requires_human_escalation",
                   "conditional_routing_rule"):
        assert tags[needed] > 0, needed
    assert Counter(m["message_type"] for m in t["message"]).keys() >= {"question", "answer", "clarification_request",
                                                                      "escalation_note", "handoff_response", "reopen_request"}
    pr = Counter(r["priority"] for r in t["ticket"])
    assert pr["normal"] > pr["high"] > 0 and pr["urgent"] < pr["normal"]          # not uniform: realistic skew
    sla = t["sla"]
    br = sum(s["resolution_breached"] for s in sla) / len(sla)
    assert 0.02 < br < 0.4


def test_retired_policy_cases_have_no_current_article(data, ctx):
    t, _ = data
    gap = [r for r in t["retrieval_result"] if r["outcome"] == "no_current_policy"]
    assert gap
    for r in gap:
        assert r["matched_article_id"] is None
        pol = ctx.policies[r["matched_policy_id"]]
        assert pol["status"] == "retired"


# ---------------------------------------------------------------- injected anomalies + ground truth
def test_each_anomaly_type_injected_at_configured_rate_on_disjoint_tickets(data, cfg):
    _, g = data
    n_each = round(cfg.anomaly_rate * cfg.tickets)
    c = Counter(a["issue_type"] for a in g["ground_truth_anomalies"])
    assert set(c) == set(ISSUE_TYPES) and all(v == n_each for v in c.values())
    tickets = [a["ticket_id"] for a in g["ground_truth_anomalies"]]
    assert len(tickets) == len(set(tickets))                                      # at most one anomaly per ticket


def test_labels_point_at_real_rows_and_record_original_and_injected(data):
    t, g = data
    ids = {"message": {m["message_id"] for m in t["message"]}, "message_claim": {m["message_id"] for m in t["message"]},
           "assignment": {a["assignment_id"] for a in t["assignment"]}, "sla": {s["sla_id"] for s in t["sla"]},
           "ticket": {r["ticket_id"] for r in t["ticket"]}}
    for a in g["ground_truth_anomalies"]:
        assert a["entity_id"] in ids[a["entity_type"]]
        assert a["original_value"] != a["injected_value"] and a["description"]
    assert len({a["label_id"] for a in g["ground_truth_anomalies"]}) == len(g["ground_truth_anomalies"])


def test_detectors_find_exactly_the_injected_cases(data, cfg):
    t, g = data
    ev = evaluate(t, g, cfg.as_of)
    for it, d in ev["detection"].items():
        assert d["injected"] > 0 and d["false_positive"] == 0 and d["false_negative"] == 0, it
    assert ev["unneeded_escalations"] == 0
    acc = ev["expected_decision_accuracy_on_clean_tickets"]
    assert acc["routing_team_pct"] == acc["priority_pct"] == acc["escalation_decision_pct"] == 100.0
    assert ev["acceptance_criteria"]["article_version_recorded_pct"] == 100.0


def test_detectors_are_silent_on_a_dataset_without_anomalies():
    t, g = generate(Config(tickets=300, articles=48, anomaly_rate=0.0))
    assert g["ground_truth_anomalies"] == []
    found = run_detectors(t, Config().as_of)["found"]
    assert all(not v for v in found.values())


def test_anomaly_mutations_preserve_volumes_and_only_touch_labelled_tickets(cfg):
    base, _ = generate(Config(tickets=300, articles=48, anomaly_rate=0.0))
    mut, g = generate(Config(tickets=300, articles=48, anomaly_rate=0.02))
    assert len(base["message"]) == len(mut["message"]) and len(base["ticket"]) == len(mut["ticket"])
    flagged = {a["ticket_id"] for a in g["ground_truth_anomalies"]}
    bm = {m["message_id"]: m for m in base["message"]}
    changed = {m["ticket_id"] for m in mut["message"] if bm[m["message_id"]]["body"] != m["body"]}
    assert changed <= flagged                                                    # no silent corruption elsewhere


def test_ground_truth_is_separate_from_inputs(data):
    t, g = data
    for tb in TABLE_ORDER:
        assert not ({c.name for c in TABLE_MAP[tb].cols} & FORBIDDEN_INPUT_COLUMNS)
    assert len(g["ground_truth_expected"]) == len(t["ticket"])
    blob = " ".join(m["body"] for m in t["message"]) + " ".join(r["subject"] for r in t["ticket"])
    assert not any(it in blob for it in ISSUE_TYPES)


def test_unauthorized_and_expired_label_semantics(data, ctx):
    t, g = data
    teams = {a["assignment_id"]: a for a in t["assignment"]}
    tk = {r["ticket_id"]: r for r in t["ticket"]}
    for a in g["ground_truth_anomalies"]:
        if a["issue_type"] == "ticket_routed_to_unauthorized_team":
            asg = teams[a["entity_id"]]
            assert asg["team_id"] == a["injected_value"]
            assert not ctx.is_authorized(asg["team_id"], tk[a["ticket_id"]]["category_id"], asg["assigned_at"].date())
        if a["issue_type"] == "answer_cites_expired_policy":
            old = ctx.articles[a["injected_value"]]
            assert old["effective_to"] is not None and ctx.articles[a["original_value"]]["version_no"] > old["version_no"]
        if a["issue_type"] == "sla_clock_ignores_business_hours":
            s = next(x for x in t["sla"] if x["sla_id"] == a["entity_id"])
            assert s["calendar_mode"] == "calendar_24x7"
