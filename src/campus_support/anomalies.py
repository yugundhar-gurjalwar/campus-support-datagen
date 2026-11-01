"""Step 5: inject labelled edge cases into an otherwise valid baseline.
Each ticket receives at most one anomaly, so a label is never ambiguous and unrelated rows are never corrupted.
Counts of messages/tickets never change; every mutation is recorded in ground-truth with original -> injected."""
from __future__ import annotations

from datetime import timedelta

from . import catalog as K
from .bizcal import add_business_minutes
from .config import Config, rng_for
from .rules import FACT_BY_KEY, Context
from .simulate import sentence_for

ORDER = ("answer_cites_expired_policy", "response_claims_unsupported_fact", "ticket_routed_to_unauthorized_team",
         "sla_clock_ignores_business_hours", "escalation_not_triggered")


def _render(ctx, art, claims, rng, intro=True):
    sents = " ".join(sentence_for(c["key"], c["value"]) for c in claims)
    return ((rng.choice(K.ANSWER_INTRO) + " ") if intro else "") + sents + \
        f" Source: {art['title']}, version {art['version_no']} (effective {art['effective_from']})."


def _first_answer(b):
    return next((m for m in b["msgs"] if m["type"] == "answer" and m["cites"] and m["claims"]), None)


# ------------------------------------------------------------------ eligibility + mutation per type
def _expired(b, ctx, rng):
    m = _first_answer(b)
    if m is None:
        return None
    cur = ctx.articles[m["cites"][0]]
    key = m["claims"][0]["key"]
    olds = [a for a in ctx.versions[cur["policy_id"]] if a["version_no"] < cur["version_no"]
            and ctx.facts[a["article_id"]].get(key) != ctx.facts[cur["article_id"]].get(key)]
    if not olds:
        return None

    def apply():
        old = olds[-1]
        m["cites"] = [old["article_id"]]
        for c in m["claims"]:
            c["value"], c["support"] = ctx.facts[old["article_id"]][c["key"]], old["article_id"]
        m["body"] = _render(ctx, old, m["claims"], rng)
        return dict(entity_type="message", entity_id=m["id"], field="message_citation.article_id",
                    original=cur["article_id"], injected=old["article_id"],
                    description=f"Answer cites expired version v{old['version_no']} (ended {old['effective_to']}) "
                                f"instead of the version in force, v{cur['version_no']}")
    return apply


def _unsupported(b, ctx, rng):
    m = _first_answer(b)
    if m is None:
        return None
    c = m["claims"][0]
    cur = ctx.articles[m["cites"][0]]
    choices = FACT_BY_KEY[c["key"]][4]
    seen = {ctx.facts[a["article_id"]].get(c["key"]) for a in ctx.versions[cur["policy_id"]]}
    pool = [v for v in choices if str(v) not in seen] or [v for v in choices if str(v) != c["value"]]
    if not pool:
        return None

    def apply():
        orig = c["value"]
        c["value"], c["support"] = str(rng.choice(pool)), None
        m["body"] = _render(ctx, cur, m["claims"], rng)
        return dict(entity_type="message_claim", entity_id=m["id"], field=f"claimed_value[{c['key']}]",
                    original=str(orig), injected=c["value"],
                    description=f"Response states {c['key']}={c['value']} which no cited source supports")
    return apply


def _unauthorized(b, ctx, rng, meta):
    if b["reasons"] or any(e["type"] in ("escalated", "reassigned") for e in b["events"]):
        return None
    d = b["ticket"]["created_at"].date()
    cat = b["ticket"]["category_id"]
    wrong = [tm for tm, r in ctx.teams.items() if r["tier"] == 1 and not ctx.is_authorized(tm, cat, d)]
    if not wrong:
        return None

    def apply():
        a = b["asgs"][0]
        orig, w = a["team_id"], rng.choice(wrong)
        a["team_id"], a["assignee_id"] = w, rng.choice(meta["handlers"][w])
        return dict(entity_type="assignment", entity_id=f"ASG-{b['ticket']['ticket_id']}-01", field="team_id",
                    original=orig, injected=w,
                    description=f"{cat} ticket routed to {w}, which is not authorised for that category")
    return apply


def _sla_wall(b, ctx, rng):
    t0 = b["ticket"]["created_at"]
    cal = ctx.calendar_for(b["asgs"][0]["team_id"])
    pol = ctx.sla_by_priority[b["ticket"]["priority"]]
    biz = add_business_minutes(cal, t0, pol["resolution_minutes"])
    wall = t0 + timedelta(minutes=pol["resolution_minutes"])
    if abs((biz - wall).total_seconds()) < 240 * 60:
        return None

    def apply():
        b["_sla_wall"] = True
        return dict(entity_type="sla", entity_id=f"SLA-{b['ticket']['ticket_id']}", field="calendar_mode",
                    original="business_hours", injected="calendar_24x7",
                    description="SLA due dates and elapsed time computed on a 24x7 clock instead of the team's business calendar")
    return apply


def _no_escalation(b, ctx, rng):
    if not b["reasons"] or not set(b["reasons"]) <= {"human_review_required", "urgent_deadline"}:
        return None
    types = [e["type"] for e in b["events"]]
    if b["outcome"] != "matched" or "escalated" not in types or "resolved" not in types or "reopened" in types:
        return None
    if not any(a["type"] == "escalation" for a in b["asgs"]):
        return None

    def apply():
        res_at = [e["at"] for e in b["events"] if e["type"] == "resolved"][-1]
        b["events"] = [e for e in b["events"] if e["type"] != "escalated" and e["reason"] != "tier2_pickup"]
        b["asgs"] = [a for a in b["asgs"] if a["type"] != "escalation"]
        b["asgs"][-1]["ended_at"], b["asgs"][-1]["end_reason"] = res_at, "resolved"
        for m in b["msgs"]:
            if m["type"] == "escalation_note":
                m["type"], m["body"] = "agent_update", "Update: we are completing your request in this office."
            elif m["type"] == "handoff_response":
                art = ctx.articles[m["cites"][0]] if m["cites"] else None
                m["type"] = "agent_update"
                m["body"] = "We reviewed the request. " + rng.choice(K.DECISIONS) + (
                    " " + _render(ctx, art, m["claims"], rng, intro=False) if art else "")
        return dict(entity_type="ticket", entity_id=b["ticket"]["ticket_id"], field="ticket_event.escalated",
                    original="present", injected="absent",
                    description=f"Required escalation ({b['reasons'][0]}) never triggered; closed by tier 1")
    return apply


def inject(bundles: list, ctx: Context, cfg: Config, meta: dict) -> list[dict]:
    rng = rng_for(cfg.seed, "anomalies")
    n_each = max(1, round(cfg.anomaly_rate * len(bundles))) if cfg.anomaly_rate > 0 else 0
    taken: set = set()
    labels = []
    fns = {"answer_cites_expired_policy": lambda b: _expired(b, ctx, rng),
           "response_claims_unsupported_fact": lambda b: _unsupported(b, ctx, rng),
           "ticket_routed_to_unauthorized_team": lambda b: _unauthorized(b, ctx, rng, meta),
           "sla_clock_ignores_business_hours": lambda b: _sla_wall(b, ctx, rng),
           "escalation_not_triggered": lambda b: _no_escalation(b, ctx, rng)}
    for issue in ORDER:
        elig = []
        for b in bundles:
            if b["ticket"]["ticket_id"] in taken:
                continue
            ap = fns[issue](b)
            if ap:
                elig.append((b, ap))
        for b, ap in rng.sample(elig, min(n_each, len(elig))):
            lab = ap()
            lab["issue_type"], lab["ticket_id"] = issue, b["ticket"]["ticket_id"]
            b["anomaly"] = dict(issue_type=issue)
            taken.add(b["ticket"]["ticket_id"])
            labels.append(lab)
    labels.sort(key=lambda l: (l["ticket_id"], l["issue_type"]))
    for i, l in enumerate(labels, 1):
        l["label_id"] = f"GT-{i:06d}"
    return labels
