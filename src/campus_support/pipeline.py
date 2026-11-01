"""Orchestrates Steps 2-7: master -> simulate -> exact volume -> inject anomalies -> derive -> flatten."""
from __future__ import annotations

from .anomalies import inject
from .config import Config
from .finalize import derive, fit_message_volume, resolve_authors
from .master import build_master
from .rules import Context
from .schema import TABLE_ORDER
from .simulate import simulate


def _flatten(bundles: list, t: dict) -> None:
    for name in ("ticket", "ticket_event", "retrieval_result", "message", "message_citation", "message_claim",
                 "assignment", "sla", "resolution_feedback"):
        t[name] = []
    cit_n = clm_n = 0
    for b in bundles:
        tid = b["ticket"]["ticket_id"]
        t["ticket"].append(b["ticket"])
        t["retrieval_result"].append(b["retrieval"])
        for e in b["events"]:
            t["ticket_event"].append(dict(
                event_id=f"EVT-{tid}-{e['seq']:03d}", ticket_id=tid, event_seq=e["seq"], event_type=e["type"],
                from_status=e["from"], to_status=e["to"], event_at=e["at"], actor_type=e["actor_type"],
                actor_id=e["actor_id"], team_id=e["team_id"], reason_code=e["reason"]))
        for m in b["msgs"]:
            t["message"].append(dict(message_id=m["id"], ticket_id=tid, message_seq=m["seq"], sender_type=m["sender_type"],
                                     sender_id=m["sender_id"], message_type=m["type"], sent_at=m["at"], body=m["body"]))
            for rank, aid in enumerate(m["cites"], 1):
                cit_n += 1
                t["message_citation"].append(dict(citation_id=f"CIT-{cit_n:06d}", message_id=m["id"], article_id=aid,
                                                  article_version_no=t["_ver"][aid], citation_rank=rank))
            for c in m["claims"]:
                clm_n += 1
                t["message_claim"].append(dict(claim_id=f"CLM-{clm_n:06d}", message_id=m["id"], fact_key=c["key"],
                                               claimed_value=c["value"], supporting_article_id=c["support"]))
        for i, a in enumerate(b["asgs"], 1):
            t["assignment"].append(dict(assignment_id=f"ASG-{tid}-{i:02d}", ticket_id=tid, assignment_seq=i,
                                        team_id=a["team_id"], assignee_id=a["assignee_id"], assignment_type=a["type"],
                                        routing_rule_id=a["rule_id"], assigned_at=a["assigned_at"],
                                        ended_at=a["ended_at"], end_reason=a["end_reason"]))
        t["sla"].append(b["sla"])
        if b["feedback"]:
            t["resolution_feedback"].append(b["feedback"])


def generate(cfg: Config):
    """Returns (tables, ground_truth). Pure function of cfg (no clocks, no global RNG)."""
    cfg.validate()
    t, meta = build_master(cfg)
    ctx = Context(t, cfg.as_of)
    bundles = simulate(cfg, t, meta, ctx)
    fit_message_volume(bundles, cfg, ctx)
    labels = inject(bundles, ctx, cfg, meta)
    for b in bundles:
        resolve_authors(b, ctx)
        derive(b, ctx, cfg)
    t["_ver"] = {a["article_id"]: a["version_no"] for a in t["knowledge_article"]}
    _flatten(bundles, t)
    del t["_ver"]
    tables = {name: t[name] for name in TABLE_ORDER}
    expected = [b["truth"] for b in bundles]
    anomalies = [dict(label_id=l["label_id"], ticket_id=l["ticket_id"], entity_type=l["entity_type"],
                      entity_id=l["entity_id"], issue_type=l["issue_type"], injected_field=l["field"],
                      original_value=l["original"], injected_value=l["injected"], description=l["description"])
                 for l in labels]
    return tables, dict(ground_truth_expected=expected, ground_truth_anomalies=anomalies)
