"""Step 8: structural validation. Reads INPUT tables only (never ground truth).
Business-rule / acceptance checks that the injected anomalies are supposed to violate live in evaluate.py."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from .bizcal import add_business_minutes, business_minutes_between
from .rules import Context
from .schema import TABLE_MAP, TABLES, TRANSITIONS


def _type_ok(typ, v):
    if typ in ("str", "text"):
        return isinstance(v, str)
    if typ == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    if typ == "float":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if typ == "bool":
        return isinstance(v, bool)
    if typ == "date":
        return isinstance(v, date) and not isinstance(v, datetime)
    return isinstance(v, datetime)


class Report:
    def __init__(self):
        self.checks = []

    def add(self, category, name, bad, total=None):
        self.checks.append(dict(category=category, name=name, passed=not bad, violations=len(bad),
                                examples=[str(x) for x in bad[:5]], checked=total))

    @property
    def passed(self):
        return all(c["passed"] for c in self.checks)

    def to_dict(self):
        return dict(passed=self.passed, checks_total=len(self.checks),
                    checks_failed=sum(not c["passed"] for c in self.checks), checks=self.checks)


def check_structure(t: dict, rep: Report) -> None:
    pks = {tb.name: {r[tb.pk] for r in t[tb.name]} for tb in TABLES}
    bad = defaultdict(list)
    n_rows = 0
    for tb in TABLES:
        rows = t[tb.name]
        n_rows += len(rows)
        if len(pks[tb.name]) != len(rows):
            bad["primary_key_unique"].append(f"{tb.name}: {len(rows) - len(pks[tb.name])} duplicate pk values")
        seen = {c.name: set() for c in tb.cols if c.unique and c.name != tb.pk}
        ut = {u: set() for u in tb.unique_together}
        for r in rows:
            for c in tb.cols:
                v = r.get(c.name)
                loc = f"{tb.name}.{c.name}[{r[tb.pk]}]"
                if v is None:
                    if c.req:
                        bad["required_not_null"].append(loc)
                    continue
                if not _type_ok(c.typ, v):
                    bad["type"].append(f"{loc}={v!r}")
                    continue
                if c.enum and v not in c.enum:
                    bad["allowed_enum"].append(f"{loc}={v!r}")
                if c.pattern and not re.search(c.pattern, v):
                    bad["id_pattern"].append(f"{loc}={v!r}")
                if (c.lo is not None and v < c.lo) or (c.hi is not None and v > c.hi):
                    bad["numeric_range"].append(f"{loc}={v!r}")
                if c.fk and v not in pks[c.fk.split(".")[0]]:
                    bad["foreign_key"].append(f"{loc}={v!r} -> {c.fk}")
                if c.name in seen:
                    if v in seen[c.name]:
                        bad["unique_column"].append(f"{loc}={v!r}")
                    seen[c.name].add(v)
            for u in ut:
                k = tuple(r.get(x) for x in u)
                if k in ut[u]:
                    bad["unique_composite"].append(f"{tb.name}{u}={k}")
                ut[u].add(k)
    for fam in ("primary_key_unique", "required_not_null", "type", "allowed_enum", "id_pattern", "numeric_range",
                "foreign_key", "unique_column", "unique_composite"):
        rep.add("structure", fam, bad[fam], n_rows)


def _by(rows, key):
    d = defaultdict(list)
    for r in rows:
        d[r[key]].append(r)
    return d


def check_domain(t: dict, as_of: datetime, rep: Report, expected: dict | None = None) -> None:
    ctx = Context(t, as_of)
    tickets = {r["ticket_id"]: r for r in t["ticket"]}
    ev = _by(t["ticket_event"], "ticket_id")
    msg = _by(t["message"], "ticket_id")
    asg = _by(t["assignment"], "ticket_id")
    sla = {r["ticket_id"]: r for r in t["sla"]}
    ret = {r["ticket_id"]: r for r in t["retrieval_result"]}
    fb = {r["ticket_id"]: r for r in t["resolution_feedback"]}
    arts = ctx.articles
    cites = _by(t["message_citation"], "message_id")
    for d in (ev, msg, asg):
        for k in d:
            d[k].sort(key=lambda r: r.get("event_seq") or r.get("message_seq") or r.get("assignment_seq"))

    if expected:
        rep.add("volume", "row_counts_match_config",
                [f"{k}: {len(t[k])} != {v}" for k, v in expected.items() if len(t[k]) != v])

    # ---------------- IDs
    bad = []
    ids = sorted(tickets)
    if ids != [f"TKT-2026-{i:06d}" for i in range(1, len(ids) + 1)]:
        bad.append("ticket ids not contiguous from TKT-2026-000001")
    ordered = [tickets[i]["created_at"] for i in ids]
    if any(a > b for a, b in zip(ordered, ordered[1:])):
        bad.append("ticket ids not chronological")
    if sorted(arts) != [f"KB-{i:06d}" for i in range(1, len(arts) + 1)]:
        bad.append("article ids not contiguous")
    for tid in tickets:
        for m in msg[tid]:
            if m["message_id"] != f"MSG-{tid}-{m['message_seq']:03d}":
                bad.append(m["message_id"])
        for e in ev[tid]:
            if e["event_id"] != f"EVT-{tid}-{e['event_seq']:03d}":
                bad.append(e["event_id"])
        for a in asg[tid]:
            if a["assignment_id"] != f"ASG-{tid}-{a['assignment_seq']:02d}":
                bad.append(a["assignment_id"])
        if sla[tid]["sla_id"] != f"SLA-{tid}" or ret[tid]["retrieval_id"] != f"RET-{tid}":
            bad.append(tid)
        if tid in fb and fb[tid]["feedback_id"] != f"FB-{tid}":
            bad.append(fb[tid]["feedback_id"])
    for p in ctx.policies.values():
        if p["domain"] != p["policy_id"].split("-")[1] or ctx.categories[p["category_id"]]["domain"] != p["domain"]:
            bad.append(p["policy_id"])
    rep.add("ids", "deterministic_id_conventions", bad, len(tickets))

    # ---------------- date ordering
    bad = []
    for tm in t["term"]:
        if not (tm["registration_open_date"] <= tm["start_date"] < tm["end_date"]):
            bad.append(tm["term_id"])
    for r in t["requester"]:
        if r["active_to"] and r["active_to"] < r["active_from"]:
            bad.append(r["requester_id"])
    for a in arts.values():
        if a["effective_to"] and a["effective_to"] < a["effective_from"]:
            bad.append(a["article_id"])
        if a["published_at"].date() > a["effective_from"]:
            bad.append(f"{a['article_id']} published after effective")
    for tid, tk in tickets.items():
        c = tk["created_at"]
        if tk["requester_deadline_at"] and tk["requester_deadline_at"] <= c:
            bad.append(f"{tid} deadline")
        es, ms = ev[tid], msg[tid]
        if es[0]["event_at"] != c or ms[0]["sent_at"] != c:
            bad.append(f"{tid} first event/message != created_at")
        if any(x["event_at"] > y["event_at"] for x, y in zip(es, es[1:])):
            bad.append(f"{tid} events not ordered")
        if any(x["sent_at"] > y["sent_at"] for x, y in zip(ms, ms[1:])):
            bad.append(f"{tid} messages not ordered")
        if ms[-1]["sent_at"] > as_of or es[-1]["event_at"] > as_of:
            bad.append(f"{tid} after as_of")
        for a in asg[tid]:
            if a["assigned_at"] < c or (a["ended_at"] and a["ended_at"] < a["assigned_at"]):
                bad.append(a["assignment_id"])
        if ret[tid]["retrieved_at"] < c:
            bad.append(f"{tid} retrieval before creation")
        s = sla[tid]
        if s["first_response_due_at"] < s["clock_start_at"] or s["resolution_due_at"] < s["first_response_due_at"]:
            bad.append(s["sla_id"])
        if tk["resolved_at"] and tk["closed_at"] and tk["closed_at"] < tk["resolved_at"]:
            bad.append(f"{tid} closed before resolved")
        if tid in fb and (tk["resolved_at"] is None or fb[tid]["submitted_at"] <= tk["resolved_at"]):
            bad.append(fb[tid]["feedback_id"])
    rep.add("dates", "date_ordering", bad, len(tickets))

    # ---------------- knowledge version chain
    bad = []
    for pid, vs in ctx.versions.items():
        pol = ctx.policies[pid]
        if [v["version_no"] for v in vs] != list(range(1, len(vs) + 1)):
            bad.append(f"{pid} version numbers")
        for i, v in enumerate(vs):
            exp_sup = vs[i - 1]["article_id"] if i else None
            if v["supersedes_article_id"] != exp_sup:
                bad.append(f"{v['article_id']} supersedes")
            if i < len(vs) - 1:
                if v["effective_to"] is None or v["effective_to"] + timedelta(days=1) != vs[i + 1]["effective_from"]:
                    bad.append(f"{v['article_id']} gap/overlap")
            cur = v["effective_from"] <= as_of.date() and (v["effective_to"] is None or v["effective_to"] >= as_of.date())
            status = "current" if cur else ("superseded" if i < len(vs) - 1 else "retired")
            if v["status"] != status:
                bad.append(f"{v['article_id']} status {v['status']}!={status}")
        last = vs[-1]
        if (pol["status"] == "retired") != (last["effective_to"] is not None and last["effective_to"] < as_of.date()):
            bad.append(f"{pid} status")
        if pol["retired_date"] != (last["effective_to"] + timedelta(days=1) if last["effective_to"] else None):
            bad.append(f"{pid} retired_date")
        if pol["first_effective_date"] != vs[0]["effective_from"]:
            bad.append(f"{pid} first_effective_date")
    rep.add("dates", "article_version_chain_contiguous", bad, len(ctx.versions))

    # ---------------- lifecycle + derived-value reconciliation
    bad_life, bad_arith, bad_join = [], [], []
    for tid, tk in tickets.items():
        es, ms, aa = ev[tid], msg[tid], asg[tid]
        status = None
        for i, e in enumerate(es, 1):
            if e["event_seq"] != i or e["from_status"] != status or TRANSITIONS.get((status, e["event_type"])) != e["to_status"]:
                bad_life.append(f"{tid} event {i} {status}->{e['event_type']}")
                break
            status = e["to_status"]
        if tk["status"] != status:
            bad_life.append(f"{tid} status {tk['status']} != {status}")
        if [m["message_seq"] for m in ms] != list(range(1, len(ms) + 1)):
            bad_life.append(f"{tid} message seq")
        if [a["assignment_seq"] for a in aa] != list(range(1, len(aa) + 1)):
            bad_life.append(f"{tid} assignment seq")
        for x, y in zip(aa, aa[1:]):
            if x["ended_at"] is None or x["ended_at"] > y["assigned_at"]:
                bad_life.append(f"{tid} overlapping assignments")
        open_a = [a for a in aa if a["ended_at"] is None]
        if len(open_a) > 1 or (tk["current_team_id"] != (open_a[-1]["team_id"] if open_a else None)):
            bad_life.append(f"{tid} current_team_id")
        if (tk["status"] in ("resolved", "closed")) and tk["resolution_code"] is None:
            bad_life.append(f"{tid} resolution_code missing")
        # ---- arithmetic
        if tk["message_count"] != len(ms):
            bad_arith.append(f"{tid} message_count")
        if tk["reopen_count"] != sum(e["event_type"] == "reopened" for e in es):
            bad_arith.append(f"{tid} reopen_count")
        if tk["escalation_count"] != sum(e["event_type"] == "escalated" for e in es):
            bad_arith.append(f"{tid} escalation_count")
        res = [e["event_at"] for e in es if e["event_type"] == "resolved"]
        if tk["resolved_at"] != (res[-1] if res else None):
            bad_arith.append(f"{tid} resolved_at")
        s = sla[tid]
        cal = ctx.cal24 if s["calendar_mode"] == "calendar_24x7" else ctx.calendars[s["calendar_id"]]
        pol = ctx.sla_policies[s["sla_policy_id"]]
        if pol["priority"] != tk["priority"] or s["clock_start_at"] != tk["created_at"]:
            bad_arith.append(f"{tid} sla policy/clock")
        if s["first_response_due_at"] != add_business_minutes(cal, s["clock_start_at"], pol["first_response_minutes"]) \
                or s["resolution_due_at"] != add_business_minutes(cal, s["clock_start_at"], pol["resolution_minutes"]):
            bad_arith.append(f"{tid} sla due")
        fr = next((m["sent_at"] for m in ms if m["sender_type"] == "support_staff"), None)
        stop = (res[0] if res else None) or tk["closed_at"] or as_of
        el_fr = business_minutes_between(cal, s["clock_start_at"], fr) if fr else None
        el_rs = business_minutes_between(cal, s["clock_start_at"], stop)
        if (s["first_response_at"], s["first_resolved_at"], s["resolution_clock_stop_at"]) != (fr, res[0] if res else None, stop):
            bad_arith.append(f"{tid} sla timestamps")
        if s["first_response_elapsed_minutes"] != el_fr or s["resolution_elapsed_minutes"] != el_rs:
            bad_arith.append(f"{tid} sla elapsed")
        if s["resolution_breached"] != (el_rs > pol["resolution_minutes"]) or (
                fr is not None and s["first_response_breached"] != (el_fr > pol["first_response_minutes"])):
            bad_arith.append(f"{tid} sla breach flags")
        # ---- joins / actors
        rq = ctx.requesters[tk["requester_id"]]
        if not ctx.roles[rq["role_id"]]["can_file_tickets"] or rq["team_id"] is not None:
            bad_join.append(f"{tid} requester cannot file")
        if rq["active_from"] > tk["created_at"].date() or (rq["active_to"] and rq["active_to"] < tk["created_at"].date()):
            bad_join.append(f"{tid} requester inactive at creation")
        if tk["term_id"] != ctx.term_for(tk["created_at"].date()):
            bad_join.append(f"{tid} term")
        for a in aa:
            h = ctx.requesters[a["assignee_id"]]
            if h["team_id"] != a["team_id"]:
                bad_join.append(f"{a['assignment_id']} assignee not in team")
            if (a["assignment_type"] == "initial") != (a["routing_rule_id"] is not None):
                bad_join.append(f"{a['assignment_id']} routing_rule_id usage")

        def who(at):
            cur = aa[0]
            for a in aa:
                if a["assigned_at"] <= at:
                    cur = a
            return cur["assignee_id"]
        for m in ms:
            if (m["sender_type"] == "system") != (m["sender_id"] is None):
                bad_join.append(f"{m['message_id']} sender")
            elif m["sender_type"] == "requester" and m["sender_id"] != tk["requester_id"]:
                bad_join.append(f"{m['message_id']} requester sender")
            elif m["sender_type"] == "support_staff" and m["sender_id"] != who(m["sent_at"]):
                bad_join.append(f"{m['message_id']} staff sender not assignee")
        for e in es:
            if e["actor_type"] == "support_staff" and e["actor_id"] != who(e["event_at"]):
                bad_join.append(f"{e['event_id']} actor not assignee")
    rep.add("lifecycle", "lifecycle_transitions_and_sequences", bad_life, len(tickets))
    rep.add("reconciliation", "derived_values_reconcile_to_source_records", bad_arith, len(tickets))
    rep.add("joins", "actor_role_term_assignment_joins", bad_join, len(tickets))

    # ---------------- citations / claims
    bad = []
    mt = {m["message_id"]: m for m in t["message"]}
    for c in t["message_citation"]:
        if c["article_version_no"] != arts[c["article_id"]]["version_no"]:
            bad.append(f"{c['citation_id']} version not recorded correctly")
    cited = {mid: {c["article_id"] for c in cs} for mid, cs in cites.items()}
    for c in t["message_claim"]:
        if c["supporting_article_id"] and c["supporting_article_id"] not in cited.get(c["message_id"], set()):
            bad.append(f"{c['claim_id']} support not cited")
        if c["fact_key"] not in {k for f in ctx.facts.values() for k in f}:
            bad.append(f"{c['claim_id']} unknown fact_key")
    for mid in cites:
        if mt[mid]["sender_type"] == "requester":
            bad.append(f"{mid} requester cites")
    rep.add("joins", "citation_and_claim_integrity", bad, len(t["message_citation"]))

    # ---------------- duplicates
    seen, bad = {}, []
    for tk in tickets.values():
        k = (tk["requester_id"], tk["category_id"], tk["created_at"], tk["subject"])
        if k in seen:
            bad.append(f"{tk['ticket_id']} duplicates {seen[k]}")
        seen[k] = tk["ticket_id"]
    seen = {}
    for m in t["message"]:
        k = (m["ticket_id"], m["sent_at"], m["body"])
        if k in seen:
            bad.append(f"{m['message_id']} duplicates {seen[k]}")
        seen[k] = m["message_id"]
    rep.add("duplicates", "no_duplicate_tickets_or_messages", bad, len(tickets) + len(t["message"]))


def validate(t: dict, as_of: datetime, expected: dict | None = None) -> Report:
    rep = Report()
    check_structure(t, rep)
    check_domain(t, as_of, rep, expected)
    return rep


def to_markdown(rep: Report, title="Validation summary") -> str:
    d = rep.to_dict()
    L = [f"# {title}", "", f"**Overall: {'PASS' if d['passed'] else 'FAIL'}** — "
         f"{d['checks_total'] - d['checks_failed']}/{d['checks_total']} checks passed", "",
         "| Category | Check | Result | Violations |", "|---|---|---|---|"]
    for c in d["checks"]:
        L.append(f"| {c['category']} | {c['name']} | {'PASS' if c['passed'] else 'FAIL'} | {c['violations']} |")
    for c in d["checks"]:
        if not c["passed"]:
            L += ["", f"### {c['name']} — examples", *[f"- {x}" for x in c["examples"]]]
    return "\n".join(L) + "\n"
