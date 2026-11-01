"""Evaluation: rule-based anomaly detectors that see INPUT tables only, scored against separate ground truth,
plus operational / acceptance-criteria metrics. Ground truth is used exclusively for scoring, never as a feature."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from .bizcal import add_business_minutes
from .rules import Context
from .schema import ISSUE_TYPES


def _pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def _q(vals, q):
    vals = sorted(v for v in vals if v is not None)
    return vals[min(len(vals) - 1, int(q * len(vals)))] if vals else None


def run_detectors(t: dict, as_of: datetime) -> dict:
    ctx = Context(t, as_of)
    tickets = {r["ticket_id"]: r for r in t["ticket"]}
    msgs = {r["message_id"]: r for r in t["message"]}
    cites = defaultdict(list)
    for c in t["message_citation"]:
        cites[c["message_id"]].append(c)
    found = {i: {} for i in ISSUE_TYPES}

    # D1: cited article not in force on the message date
    for c in t["message_citation"]:
        m = msgs[c["message_id"]]
        a = ctx.articles[c["article_id"]]
        d = m["sent_at"].date()
        if not (a["effective_from"] <= d and (a["effective_to"] is None or a["effective_to"] >= d)):
            found["answer_cites_expired_policy"][m["ticket_id"]] = c["message_id"]
    # D3: claim not matched by any cited article's fact
    for cl in t["message_claim"]:
        m = msgs[cl["message_id"]]
        ok = any(ctx.facts.get(c["article_id"], {}).get(cl["fact_key"]) == cl["claimed_value"] for c in cites[cl["message_id"]])
        if not ok:
            found["response_claims_unsupported_fact"][m["ticket_id"]] = cl["message_id"]
    # D2: team not authorised for category, or initial team differs from routing-rule target
    for a in t["assignment"]:
        tk = tickets[a["ticket_id"]]
        d = a["assigned_at"].date()
        bad = not ctx.is_authorized(a["team_id"], tk["category_id"], d)
        if a["assignment_type"] == "initial":
            rule = ctx.route(tk["category_id"], ctx.requesters[tk["requester_id"]]["role_id"], tk["created_at"].date())
            bad = bad or rule["target_team_id"] != a["team_id"] or rule["routing_rule_id"] != a["routing_rule_id"]
        if bad:
            found["ticket_routed_to_unauthorized_team"][a["ticket_id"]] = a["assignment_id"]
    # D4: SLA due dates not reproducible on the declared business calendar
    for s in t["sla"]:
        pol = ctx.sla_policies[s["sla_policy_id"]]
        cal = ctx.calendars[s["calendar_id"]]
        if s["calendar_mode"] != "business_hours" or \
                s["first_response_due_at"] != add_business_minutes(cal, s["clock_start_at"], pol["first_response_minutes"]) or \
                s["resolution_due_at"] != add_business_minutes(cal, s["clock_start_at"], pol["resolution_minutes"]):
            found["sla_clock_ignores_business_hours"][s["ticket_id"]] = s["sla_id"]
    # D5: documented escalation rules require escalation but no 'escalated' event exists
    escalated = {e["ticket_id"] for e in t["ticket_event"] if e["event_type"] == "escalated"}
    over = []
    for r in t["retrieval_result"]:
        tk = tickets[r["ticket_id"]]
        dl = None if tk["requester_deadline_at"] is None else (tk["requester_deadline_at"] - tk["created_at"]).total_seconds() / 3600
        reasons = ctx.escalation_reasons(tk["category_id"], r["outcome"], dl)
        if reasons and r["ticket_id"] not in escalated:
            found["escalation_not_triggered"][r["ticket_id"]] = reasons[0]
        if not reasons and r["ticket_id"] in escalated:
            over.append(r["ticket_id"])
    return dict(found=found, unneeded_escalations=over)


def evaluate(t: dict, ground: dict, as_of: datetime) -> dict:
    det = run_detectors(t, as_of)
    found = det["found"]
    truth = defaultdict(set)
    for a in ground["ground_truth_anomalies"]:
        truth[a["issue_type"]].add(a["ticket_id"])
    detection = {}
    for it in ISSUE_TYPES:
        f, g = set(found[it]), truth[it]
        tp, fp, fn = len(f & g), len(f - g), len(g - f)
        detection[it] = dict(injected=len(g), detected=len(f), true_positive=tp, false_positive=fp, false_negative=fn,
                             precision=round(tp / (tp + fp), 4) if tp + fp else None,
                             recall=round(tp / (tp + fn), 4) if tp + fn else None)

    ctx = Context(t, as_of)
    tickets = {r["ticket_id"]: r for r in t["ticket"]}
    first_asg = {}
    for a in sorted(t["assignment"], key=lambda r: (r["ticket_id"], r["assignment_seq"])):
        first_asg.setdefault(a["ticket_id"], a)
    exp = {e["ticket_id"]: e for e in ground["ground_truth_expected"]}
    escalated = {e["ticket_id"] for e in t["ticket_event"] if e["event_type"] == "escalated"}
    flagged = {tid for it in ISSUE_TYPES for tid in truth[it]}

    # ---- accuracy vs expected decisions (clean tickets should match exactly)
    clean = [tid for tid in tickets if tid not in flagged]
    team_ok = sum(first_asg[tid]["team_id"] == exp[tid]["expected_team_id"] for tid in clean)
    prio_ok = sum(tickets[tid]["priority"] == exp[tid]["expected_priority"] for tid in clean)
    esc_ok = sum((tid in escalated) == exp[tid]["expected_escalation"] for tid in clean)
    reason_conf = Counter(exp[tid]["expected_escalation_reason"] or "none" for tid in tickets)

    # ---- acceptance criteria (measured over ALL data, injected defects included)
    answers = [m for m in t["message"] if m["message_type"] == "answer"]
    cit_by_msg = defaultdict(list)
    for c in t["message_citation"]:
        cit_by_msg[c["message_id"]].append(c)
    bad_msgs = {mid for mid in found["answer_cites_expired_policy"].values()}
    a_current = sum(1 for m in answers if m["message_id"] not in bad_msgs and cit_by_msg[m["message_id"]])
    a_cited = sum(1 for m in answers if cit_by_msg[m["message_id"]])
    routed_ok = len(tickets) - len(found["ticket_routed_to_unauthorized_team"])
    need_esc = [r for r in t["retrieval_result"]
                if ctx.escalation_reasons(tickets[r["ticket_id"]]["category_id"], r["outcome"],
                                          None if tickets[r["ticket_id"]]["requester_deadline_at"] is None else
                                          (tickets[r["ticket_id"]]["requester_deadline_at"] - tickets[r["ticket_id"]]["created_at"]).total_seconds() / 3600)]
    esc_done = sum(1 for r in need_esc if r["ticket_id"] in escalated)
    ver_ok = sum(1 for c in t["message_citation"] if c["article_version_no"] == ctx.articles[c["article_id"]]["version_no"])
    acceptance = {
        "answers_cite_current_sources_pct": _pct(a_current, len(answers)),
        "routing_consistent_pct": _pct(routed_ok, len(tickets)),
        "unresolved_or_ambiguous_escalated_pct": _pct(esc_done, len(need_esc)),
        "article_version_recorded_pct": _pct(ver_ok, len(t["message_citation"])),
        "answers_with_at_least_one_citation_pct": _pct(a_cited, len(answers)),
    }

    # ---- operational metrics
    sla = t["sla"]
    by_prio = defaultdict(list)
    for s in sla:
        by_prio[tickets[s["ticket_id"]]["priority"]].append(s)
    sla_by_priority = {p: dict(tickets=len(v), first_response_breach_pct=_pct(sum(x["first_response_breached"] for x in v), len(v)),
                               resolution_breach_pct=_pct(sum(x["resolution_breached"] for x in v), len(v)),
                               median_first_response_min=_q([x["first_response_elapsed_minutes"] for x in v], 0.5),
                               p90_first_response_min=_q([x["first_response_elapsed_minutes"] for x in v], 0.9))
                       for p, v in sorted(by_prio.items())}
    fb = t["resolution_feedback"]
    rating_by_flag = defaultdict(list)
    for f in fb:
        rating_by_flag["anomalous" if f["ticket_id"] in flagged else "clean"].append(f["rating"])
    tags = Counter(tag for e in ground["ground_truth_expected"] for tag in (e["case_tags"] or "").split("|") if tag)
    ops = dict(
        tickets=len(tickets), by_status=dict(Counter(r["status"] for r in t["ticket"])),
        by_domain=dict(Counter(ctx.categories[r["category_id"]]["domain"] for r in t["ticket"])),
        by_priority=dict(Counter(r["priority"] for r in t["ticket"])),
        by_channel=dict(Counter(r["channel"] for r in t["ticket"])),
        escalation_rate_pct=_pct(len(escalated), len(tickets)),
        escalations_by_reason=dict(Counter(e["reason_code"] for e in t["ticket_event"] if e["event_type"] == "escalated")),
        reopen_rate_pct=_pct(sum(1 for r in t["ticket"] if r["reopen_count"] > 0), len(tickets)),
        resolution_codes=dict(Counter(r["resolution_code"] or "open" for r in t["ticket"])),
        sla_by_priority=sla_by_priority,
        feedback_rate_pct=_pct(len(fb), sum(1 for r in t["ticket"] if r["resolved_at"])),
        mean_rating=round(sum(f["rating"] for f in fb) / len(fb), 3) if fb else None,
        mean_rating_by_group={k: round(sum(v) / len(v), 3) for k, v in rating_by_flag.items()},
        messages_per_ticket=round(len(t["message"]) / len(tickets), 3),
        citations=len(t["message_citation"]), claims=len(t["message_claim"]),
        case_coverage_tags=dict(tags))
    return dict(
        detection=detection, unneeded_escalations=len(det["unneeded_escalations"]),
        expected_decision_accuracy_on_clean_tickets=dict(
            tickets=len(clean), routing_team_pct=_pct(team_ok, len(clean)), priority_pct=_pct(prio_ok, len(clean)),
            escalation_decision_pct=_pct(esc_ok, len(clean))),
        expected_escalation_reasons=dict(reason_conf), acceptance_criteria=acceptance, operations=ops)


def to_markdown(ev: dict) -> str:
    L = ["# Evaluation report", "", "## Anomaly detection (rule-based detectors on input tables vs ground truth)", "",
         "| Issue type | Injected | Detected | TP | FP | FN | Precision | Recall |", "|---|---|---|---|---|---|---|---|"]
    for k, d in ev["detection"].items():
        L.append(f"| {k} | {d['injected']} | {d['detected']} | {d['true_positive']} | {d['false_positive']} | "
                 f"{d['false_negative']} | {d['precision']} | {d['recall']} |")
    L += ["", f"Escalations with no documented trigger (over-escalation): **{ev['unneeded_escalations']}**", "",
          "## Acceptance criteria (all data, injected defects included)", "", "| Criterion | % |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in ev["acceptance_criteria"].items()]
    a = ev["expected_decision_accuracy_on_clean_tickets"]
    L += ["", "## Generator conformance on clean (non-injected) tickets", "",
          f"- tickets: {a['tickets']}; routing team = expected: {a['routing_team_pct']}%; priority = expected: "
          f"{a['priority_pct']}%; escalation decision = expected: {a['escalation_decision_pct']}%", "",
          "## Operations", ""]
    o = ev["operations"]
    L += [f"- tickets: {o['tickets']}; messages/ticket: {o['messages_per_ticket']}; escalation rate: {o['escalation_rate_pct']}%; "
          f"reopen rate: {o['reopen_rate_pct']}%; feedback rate: {o['feedback_rate_pct']}%; mean rating: {o['mean_rating']}",
          f"- by status: {o['by_status']}", f"- by domain: {o['by_domain']}", f"- by priority: {o['by_priority']}",
          f"- escalations by reason: {o['escalations_by_reason']}", f"- resolution codes: {o['resolution_codes']}",
          f"- mean rating by group: {o['mean_rating_by_group']}", f"- case coverage tags: {o['case_coverage_tags']}", "",
          "| Priority | Tickets | FR breach % | Resolution breach % | Median FR (min) | P90 FR (min) |", "|---|---|---|---|---|---|"]
    for p, v in o["sla_by_priority"].items():
        L.append(f"| {p} | {v['tickets']} | {v['first_response_breach_pct']} | {v['resolution_breach_pct']} | "
                 f"{v['median_first_response_min']} | {v['p90_first_response_min']} |")
    return "\n".join(L) + "\n"
