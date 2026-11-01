"""Post-skeleton passes: exact message-volume fitting, author resolution and derived values (Step 6).
Everything computed here is derived from event / assignment / message records, never drawn independently."""
from __future__ import annotations

from datetime import timedelta

from . import catalog as K
from .bizcal import add_business_minutes, business_minutes_between
from .config import Config, rng_for
from .rules import Context
from .schema import TRANSITIONS

M = lambda x: timedelta(minutes=int(x))
MAX_EXTRAS = 6


# ------------------------------------------------------------------ extras (exact volume)
def _try_insert(b: dict, rng, as_of) -> bool:
    msgs = sorted(b["msgs"], key=lambda m: m["at"])
    first_staff = next((i for i, m in enumerate(msgs) if m["who"] == "staff"), len(msgs))
    cands = []
    if not any(m["type"] == "system_ack" for m in msgs) and len(msgs) > 1 \
            and (msgs[1]["at"] - msgs[0]["at"]).total_seconds() >= 5 * 60:
        cands.append(("system_ack", 0, msgs[0]["at"] + M(1), msgs[0]["at"] + M(4)))
    for i in range(len(msgs) - 1):
        a, c = msgs[i], msgs[i + 1]
        if (c["at"] - a["at"]).total_seconds() < 15 * 60:
            continue
        if a["type"] in ("answer", "handoff_response") and c["type"] == "reopen_request":
            continue
        if a["who"] == "staff":
            typ = "requester_followup"
        else:
            typ = "requester_followup" if i < first_staff else "agent_update"
        cands.append((typ, i, a["at"] + M(4), c["at"] - M(4)))
    last = msgs[-1]
    resolved = [e["at"] for e in b["events"] if e["type"] == "resolved"]
    if resolved and last["who"] == "staff" and last["type"] in ("answer", "handoff_response") \
            and not any(m["type"] == "thanks" for m in msgs):
        hi = min(resolved[-1] + timedelta(days=6), as_of)
        cands.append(("thanks", len(msgs) - 1, last["at"] + M(3), hi))
    cands = [c for c in cands if c[3] > c[2]]
    if not cands:
        return False
    typ, _, lo, hi = rng.choice(cands)
    at = lo + M(rng.randint(0, int((hi - lo).total_seconds() / 60)))
    if typ == "system_ack":
        body = rng.choice(K.SYSTEM_ACK).format(tid=b["ticket"]["ticket_id"], team=b["_team1_name"])
        who = "system"
    elif typ == "requester_followup":
        body, who = rng.choice(K.FOLLOWUP), "requester"
    elif typ == "thanks":
        body, who = rng.choice(K.THANKS), "requester"
    else:
        body, who = rng.choice(K.ACK), "staff"
    b["msgs"].append(dict(type=typ, at=at, who=who, body=body, cites=[], claims=[]))
    b["extras"] = b.get("extras", 0) + 1
    return True


def fit_message_volume(bundles: list, cfg: Config, ctx: Context) -> None:
    rng = rng_for(cfg.seed, "extras")
    for b in bundles:
        b["_team1_name"] = ctx.teams[b["team1"]]["team_name"]
    need = cfg.messages - sum(len(b["msgs"]) for b in bundles)
    if need < 0:
        raise ValueError(f"structural messages exceed target by {-need}; raise --messages-per-ticket")
    weights = [1 + 0.6 * bool(b["reasons"]) + 0.4 * (b["prof"]["amb"] > 0) + 0.3 * b["prof"]["reopen"] for b in bundles]
    attempts = 0
    while need > 0:
        attempts += 1
        if attempts > 60 * len(bundles):
            raise RuntimeError(f"could not place {need} extra messages; lower --messages-per-ticket")
        b = rng.choices(bundles, weights)[0]
        if b.get("extras", 0) < MAX_EXTRAS and _try_insert(b, rng, cfg.as_of):
            need -= 1
    for b in bundles:
        b["msgs"].sort(key=lambda m: m["at"])
        for i, m in enumerate(b["msgs"], 1):
            m["seq"] = i
            m["id"] = f"MSG-{b['ticket']['ticket_id']}-{i:03d}"


# ------------------------------------------------------------------ authors
def assignee_at(b: dict, t):
    cur = b["asgs"][0]
    for a in b["asgs"]:
        if a["assigned_at"] <= t:
            cur = a
    return cur


def resolve_authors(b: dict, ctx: Context) -> None:
    rid = b["ticket"]["requester_id"]
    for e in b["events"]:
        w = e["who"]
        if w == "requester":
            e["actor_type"], e["actor_id"], e["team_id"] = "requester", rid, None
        elif w == "system":
            e["actor_type"], e["actor_id"] = "system", None
            e["team_id"] = b["asgs"][0]["team_id"] if e["type"] == "routed" else None
        else:
            a = assignee_at(b, e["at"])
            e["actor_type"], e["actor_id"] = "support_staff", a["assignee_id"]
            e["team_id"] = ctx.teams[a["team_id"]]["escalation_team_id"] if e["type"] == "escalated" else a["team_id"]
    for m in b["msgs"]:
        if m["who"] == "requester":
            m["sender_type"], m["sender_id"] = "requester", rid
        elif m["who"] == "system":
            m["sender_type"], m["sender_id"] = "system", None
        else:
            m["sender_type"], m["sender_id"] = "support_staff", assignee_at(b, m["at"])["assignee_id"]


# ------------------------------------------------------------------ derived values
def derive(b: dict, ctx: Context, cfg: Config) -> None:
    ev = b["events"]
    status = None
    for i, e in enumerate(ev, 1):
        key = (status, e["type"])
        if key not in TRANSITIONS:
            raise AssertionError(f"{b['ticket']['ticket_id']}: illegal transition {key}")
        e["seq"], e["from"], status = i, status, TRANSITIONS[key]
        e["to"] = status
    tk = b["ticket"]
    resolved = [e["at"] for e in ev if e["type"] == "resolved"]
    closed = [e for e in ev if e["type"] == "closed"]
    open_asg = [a for a in b["asgs"] if a["ended_at"] is None]
    esc = sum(1 for e in ev if e["type"] == "escalated")
    code = None
    if closed and closed[0]["reason"] == "no_response":
        code = "closed_no_response"
    elif resolved:
        code = "resolved_after_escalation" if esc else "answered_by_policy"
    tk.update(status=status, current_team_id=open_asg[-1]["team_id"] if open_asg else None,
              resolved_at=resolved[-1] if resolved else None, closed_at=closed[0]["at"] if closed else None,
              resolution_code=code, reopen_count=sum(1 for e in ev if e["type"] == "reopened"),
              escalation_count=esc, message_count=len(b["msgs"]))

    # ---- SLA: clock built from the routed team's calendar, elapsed/breach from events + messages
    t0 = tk["created_at"]
    cal_true = ctx.calendar_for(b["asgs"][0]["team_id"])
    wall = b["anomaly"] is not None and b["anomaly"]["issue_type"] == "sla_clock_ignores_business_hours"
    cal = ctx.cal24 if wall else cal_true
    pol = ctx.sla_by_priority[tk["priority"]]
    fr_at = next((m["at"] for m in b["msgs"] if m["who"] == "staff"), None)
    first_res = resolved[0] if resolved else None
    stop = first_res or tk["closed_at"] or cfg.as_of
    due_fr = add_business_minutes(cal, t0, pol["first_response_minutes"])
    due_rs = add_business_minutes(cal, t0, pol["resolution_minutes"])
    el_fr = business_minutes_between(cal, t0, fr_at) if fr_at else None
    el_rs = business_minutes_between(cal, t0, stop)
    b["sla"] = dict(sla_id=f"SLA-{tk['ticket_id']}", ticket_id=tk["ticket_id"], sla_policy_id=pol["sla_policy_id"],
                    calendar_id=cal.calendar_id if not wall else cal_true.calendar_id,
                    calendar_mode="calendar_24x7" if wall else "business_hours",
                    clock_start_at=t0, first_response_due_at=due_fr, resolution_due_at=due_rs,
                    first_response_at=fr_at, first_resolved_at=first_res, resolution_clock_stop_at=stop,
                    first_response_elapsed_minutes=el_fr, resolution_elapsed_minutes=el_rs,
                    first_response_breached=(el_fr > pol["first_response_minutes"]) if fr_at is not None
                    else cfg.as_of > due_fr,
                    resolution_breached=el_rs > pol["resolution_minutes"])

    # ---- feedback: rule score from the TRUE business-hours clock (what the requester experienced)
    n = int(tk["ticket_id"].split("-")[-1])
    rng = rng_for(cfg.seed, f"feedback:{n}")
    b["feedback"] = None
    if tk["resolved_at"] is None or rng.random() >= 0.55:
        return
    at = tk["resolved_at"] + M(rng.randint(30, 72 * 60))
    if at > cfg.as_of:
        return
    el_fr_t = business_minutes_between(cal_true, t0, fr_at) if fr_at else 0
    el_rs_t = business_minutes_between(cal_true, t0, stop)
    fr_br, rs_br = el_fr_t > pol["first_response_minutes"], el_rs_t > pol["resolution_minutes"]
    wrong = b["anomaly"] is not None and b["anomaly"]["issue_type"] in (
        "answer_cites_expired_policy", "response_claims_unsupported_fact")
    score = 5 - fr_br - rs_br - (tk["reopen_count"] > 0) - wrong - (tk["escalation_count"] > 0 and rng.random() < 0.5)
    if rng.random() < 0.25:
        score += rng.choice([-1, 1])
    score = max(1, min(5, score))
    if rng.random() < 0.3:
        code = "none"
    elif score >= 4:
        code = "fast_and_clear" if not (fr_br or rs_br) else "helpful"
    elif wrong:
        code = "wrong_or_outdated"
    elif tk["reopen_count"] > 0 and score <= 2:
        code = "unresolved"
    else:
        code = "slow" if (fr_br or rs_br) else "unclear"
    b["feedback"] = dict(feedback_id=f"FB-{tk['ticket_id']}", ticket_id=tk["ticket_id"], submitted_at=at,
                         rating=score, issue_resolved=tk["reopen_count"] == 0, comment_code=code)
