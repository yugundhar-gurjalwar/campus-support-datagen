"""Step 2b: transaction/event generation. Outcomes follow the documented rules in rules.py:
profiles only draw *intake* attributes (category, requester, topic, vagueness, deadline); routing, priority,
retrieval outcome, escalation, SLA and resolution are then derived from those via rules."""
from __future__ import annotations

import itertools
import math
from datetime import date, datetime, time, timedelta

from . import catalog as K
from .bizcal import add_business_minutes as bm
from .config import Config, rng_for
from .rules import (CONF_CLARIFY, FACT_BY_KEY, NO_REPLY_WAIT_MINUTES, STALL_CLOSE_MINUTES, Context)

M = lambda x: timedelta(minutes=int(x))
_DOW = [1.25, 1.2, 1.1, 1.1, 0.95, 0.3, 0.2]
_HOURS = list(range(7, 23))
_HW = [1, 3, 6, 7, 7, 6, 5, 6, 7, 6, 4, 3, 2, 1.5, 1.2, 1]
_TERM_STARTS = [date(2026, 1, 12), date(2026, 5, 18), date(2026, 8, 24)]


def lognorm(rng, median, sigma):
    return median * math.exp(rng.gauss(0, sigma))


def _day_weight(d: date, domain: str, holidays: set) -> float:
    w = _DOW[d.weekday()]
    if d in holidays:
        w *= 0.15
    for s in _TERM_STARTS:
        off = (d - s).days
        if domain in ("REG", "FIN") and -7 <= off <= 14:
            w *= 2.2
        if domain == "IT" and 0 <= off <= 10:
            w *= 1.8
    if domain in ("REG", "FIN") and date(2026, 8, 8) <= d <= date(2026, 8, 31):
        w *= 1.5
    return w


# ------------------------------------------------------------------ profiles
def make_profiles(cfg: Config, ctx: Context, t: dict, meta: dict) -> list[dict]:
    rng = rng_for(cfg.seed, "ticket_profiles")
    holidays = {r["holiday_date"] for r in t["holiday"]}
    days = [cfg.window_start + timedelta(days=i) for i in range((cfg.window_end - cfg.window_start).days + 1)]
    day_cum = {dom: list(itertools.accumulate(_day_weight(d, dom, holidays) for d in days)) for dom in K.DOMAIN_TEAM}
    cats = K.CATEGORIES
    cat_cum = list(itertools.accumulate(c[7] for c in cats))
    pools = {}
    for role in ("ROLE-LEARNER", "ROLE-INSTRUCTOR", "ROLE-ACADADMIN"):
        ids = [r["requester_id"] for r in t["requester"] if r["role_id"] == role and r["team_id"] is None]
        pools[role] = (ids, list(itertools.accumulate(meta["req_weight"][i] for i in ids)))

    def pick_requester(role, d):
        ids, cum = pools[role]
        for _ in range(80):
            rid = rng.choices(ids, cum_weights=cum)[0]
            r = ctx.requesters[rid]
            if r["active_from"] <= d and (r["active_to"] is None or r["active_to"] >= d):
                return rid
        return next(i for i in ids if ctx.requesters[i]["active_from"] <= d
                    and (ctx.requesters[i]["active_to"] is None or ctx.requesters[i]["active_to"] >= d))

    profs = []
    for _ in range(cfg.tickets):
        cat = rng.choices(cats, cum_weights=cat_cum)[0]
        dom = cat[1]
        d = rng.choices(days, cum_weights=day_cum[dom])[0]
        hw = [w * (2.0 if (dom == "IT" and h >= 18) else 1.0) for h, w in zip(_HOURS, _HW)]
        created = datetime.combine(d, time(rng.choices(_HOURS, hw)[0], rng.randint(0, 59)))
        role = rng.choices(["ROLE-LEARNER", "ROLE-INSTRUCTOR", "ROLE-ACADADMIN"], K.ROLE_MIX_BY_DOMAIN[dom])[0]
        rid = pick_requester(role, d)
        cands = ctx.policies_by_category[cat[0]]
        ws = []
        for pid in cands:
            rd = meta["retired"].get(pid)
            w = 1.0
            if rd and d >= rd:
                w = 0.6                       # asking about a withdrawn policy -> "no current policy" case
            elif rd and (rd - d).days < 30:
                w = 0.0                       # avoid answers straddling the withdrawal date
            if w and any(0 < (v["effective_from"] - d).days <= 3 for v in ctx.versions[pid][1:]):
                w *= 8.0                      # boundary coverage: a new version takes effect within days of the ticket
            ws.append(w)
        if sum(ws) == 0:
            ws = [1.0] * len(cands)
        pid = rng.choices(cands, ws)[0]
        pfacts = [f for f in ctx.facts[ctx.versions[pid][0]["article_id"]]]
        fact_key = rng.choice(pfacts)
        has_art = ctx.effective_article(pid, d) is not None
        amb = 0 if not has_art else rng.choices([0, 1, 2], [80, 14, 6])[0]
        dl_at = None
        if rng.random() < 0.14:
            x = rng.random()
            hrs = rng.uniform(2, 24) if x < 0.35 else (rng.uniform(24.5, 72) if x < 0.75 else rng.uniform(73, 240))
            dl_at = created + M(round(hrs * 60))
        if dom == "IT":
            channel = rng.choices(["portal", "email", "chat", "phone"], [35, 15, 40, 10])[0]
        else:
            channel = rng.choices(["portal", "email", "chat", "phone"], [55, 25, 15, 5])[0]
        profs.append(dict(created=created, cat=cat[0], role=role, requester=rid, policy=pid, fact=fact_key,
                          amb=amb, deadline_at=dl_at, channel=channel, stall=rng.random() < 0.25,
                          reopen=rng.random() < 0.04, reassign=rng.random() < 0.04, ack=rng.random() < 0.45))
    profs.sort(key=lambda p: (p["created"], p["cat"], p["requester"]))
    return profs


# ------------------------------------------------------------------ text helpers
def _humanize(key: str) -> str:
    return key.replace("_", " ")


def _make_answer(ctx, policy_id, fact_key, at, rng, intro=True):
    art = ctx.effective_article(policy_id, at.date())
    if art is None:
        return None
    facts = ctx.facts[art["article_id"]]
    keys = [fact_key] + [k for k in facts if k != fact_key][: (1 if rng.random() < 0.5 else 0)]
    sents = [FACT_BY_KEY[k][2].format(v=facts[k]) for k in keys]
    body = ((rng.choice(K.ANSWER_INTRO) + " ") if intro else "") + " ".join(sents) + \
        f" Source: {art['title']}, version {art['version_no']} (effective {art['effective_from']})."
    return dict(body=body, cites=[art["article_id"]],
                claims=[dict(key=k, value=facts[k], support=art["article_id"]) for k in keys])


def sentence_for(fact_key: str, value) -> str:
    return FACT_BY_KEY[fact_key][2].format(v=value)


# ------------------------------------------------------------------ skeleton
def build_bundle(n: int, p: dict, ctx: Context, meta: dict, cfg: Config) -> dict:
    rng = rng_for(cfg.seed, f"ticket:{n}")
    as_of = cfg.as_of
    ok = lambda x: x <= as_of
    tid = f"TKT-2026-{n:06d}"
    cat = ctx.categories[p["cat"]]
    t0 = p["created"]
    dl_hours = None if p["deadline_at"] is None else (p["deadline_at"] - t0).total_seconds() / 3600
    rule = ctx.route(p["cat"], p["role"], t0.date())
    team1 = rule["target_team_id"]
    tier2 = ctx.teams[team1]["escalation_team_id"]
    cal1, cal2 = ctx.calendar_for(team1), ctx.calendar_for(tier2)
    prio = ctx.priority(p["cat"], dl_hours, rule)
    slap = ctx.sla_by_priority[prio]
    res_t = slap["resolution_minutes"]
    art0 = ctx.effective_article(p["policy"], t0.date())

    a = p["amb"]
    if a == 0:
        c_init = rng.uniform(0.72, 0.97)
        c_fin = c_init
    elif a == 1:
        c_init, c_fin = rng.uniform(0.46, 0.69), rng.uniform(0.72, 0.9)
    else:
        c_init, c_fin = rng.uniform(0.20, 0.44), rng.uniform(0.25, 0.44)
    outcome = Context.retrieval_outcome(art0 is not None, c_fin)
    reasons = ctx.escalation_reasons(p["cat"], outcome, dl_hours)

    ev, msgs, asgs = [], [], []
    E = lambda typ, at, who, reason=None: ev.append(dict(type=typ, at=at, who=who, reason=reason))

    def MSG(typ, at, who, body, ans=None):
        msgs.append(dict(type=typ, at=at, who=who, body=body, cites=list(ans["cites"]) if ans else [],
                         claims=list(ans["claims"]) if ans else []))

    q = FACT_BY_KEY[p["fact"]][1]
    cname = cat["category_name"].lower()
    if a == 0:
        qtext = rng.choice(K.Q_CLEAR).format(q=q)
        subject = f"{cat['category_name']}: {_humanize(p['fact'])}"
    elif a == 1:
        qtext = rng.choice(K.Q_MODERATE).format(topic=cname)
        subject = f"Question about {cname}"
    else:
        qtext = rng.choice(K.Q_VAGUE)
        subject = rng.choice(K.SUBJ_VAGUE)
    if p["deadline_at"]:
        qtext += " " + rng.choice(K.DEADLINE_TAILS).format(when=p["deadline_at"].strftime("%b %d at %H:%M"))

    E("created", t0, "requester")
    MSG("question", t0, "requester", qtext)
    E("routed", t0 + M(1), "system", "routing_rule")
    h1 = rng.choice(meta["handlers"][team1])
    assigned_at = max(t0 + M(3), bm(cal1, t0, rng.randint(2, 45)))
    asgs.append(dict(team_id=team1, assignee_id=h1, type="initial", rule_id=rule["routing_rule_id"],
                     assigned_at=assigned_at, ended_at=None, end_reason=None))
    E("assigned", assigned_at, "staff", "initial_pickup")
    frac = 0.30 if prio == "urgent" else 0.35
    fr_bm = min(max(5, int(lognorm(rng, frac * slap["first_response_minutes"], 0.7))), 6 * slap["first_response_minutes"])
    fr_at = max(assigned_at + M(3), bm(cal1, t0, fr_bm))

    st = dict(resolved=None, first_resolved=None, closed=False, escalate_at=None)

    def clar_req(at):
        topics = [c for c in ctx.categories.values() if c["domain"] == cat["domain"]]
        rng.shuffle(topics)
        names = ", ".join(c["category_name"].lower() for c in topics[:3])
        MSG("clarification_request", at, "staff", rng.choice(K.CLARIFY_REQ).format(topics=names))
        E("clarification_requested", at, "staff", "needs_clarification")

    def tier1_answer(ans_at):
        if not ok(ans_at):
            return
        ans = _make_answer(ctx, p["policy"], p["fact"], ans_at, rng)
        MSG("answer", ans_at, "staff", ans["body"], ans)
        if reasons:
            esc_at = max(ans_at + M(5), bm(cal1, ans_at, rng.randint(20, 180)))
            if ok(esc_at):
                MSG("escalation_note", esc_at, "staff",
                    f"I am escalating this to the {ctx.teams[tier2]['team_name']} because {K.ESC_TEXT[reasons[0]]}.")
                st["escalate_at"] = esc_at
        else:
            r_at = ans_at + M(2)
            if ok(r_at):
                E("resolved", r_at, "staff", "policy_answer")
                st["resolved"] = st["first_resolved"] = r_at

    if outcome == "no_current_policy":
        MSG("escalation_note", fr_at, "staff",
            f"I could not find a current policy for this, so I am escalating to the {ctx.teams[tier2]['team_name']} "
            f"because {K.ESC_TEXT[reasons[0]]}.")
        st["escalate_at"] = fr_at
    elif a == 2:
        clar_req(fr_at)
        reply_at = fr_at + M(min(4000, max(20, int(lognorm(rng, 360, 0.9)))))
        if ok(reply_at):
            MSG("clarification_reply", reply_at, "requester", rng.choice(K.CLARIFY_VAGUE))
            E("clarification_received", reply_at, "requester", "clarification_provided")
            cr2 = max(reply_at + M(5), bm(cal1, reply_at, rng.randint(30, 240)))
            if ok(cr2):
                clar_req(cr2)
                esc_at = bm(cal1, cr2, NO_REPLY_WAIT_MINUTES)
                if ok(esc_at):
                    MSG("escalation_note", esc_at, "staff",
                        f"Escalating to the {ctx.teams[tier2]['team_name']} because {K.ESC_TEXT[reasons[0]]}.")
                    st["escalate_at"] = esc_at
    elif a == 1:
        clar_req(fr_at)
        if p["stall"] and not reasons:
            close_at = bm(cal1, fr_at, STALL_CLOSE_MINUTES)
            if ok(close_at):
                E("closed", close_at, "system", "no_response")
                st["closed"] = True
        else:
            reply_at = fr_at + M(min(4000, max(20, int(lognorm(rng, 360, 0.9)))))
            if ok(reply_at):
                MSG("clarification_reply", reply_at, "requester",
                    rng.choice(K.CLARIFY_OK).format(topic=cname, q=q))
                E("clarification_received", reply_at, "requester", "clarification_provided")
                d_bm = min(max(10, int(lognorm(rng, 0.2 * res_t, 0.8))), 2 * res_t)
                tier1_answer(max(reply_at + M(5), bm(cal1, reply_at, d_bm)))
    else:
        if reasons or not p["ack"]:
            tier1_answer(fr_at)
        else:
            MSG("agent_update", fr_at, "staff", rng.choice(K.ACK))
            r_bm = min(max(15, int(lognorm(rng, 0.28 * res_t, 0.8))), 3 * res_t)
            tier1_answer(max(fr_at + M(10), bm(cal1, t0, r_bm)))

    # ---- tier-2 handling
    if st["escalate_at"] is not None and ok(st["escalate_at"]):
        esc_at = st["escalate_at"]
        E("escalated", esc_at, "staff", reasons[0])
        as2 = max(esc_at + M(5), bm(cal2, esc_at, rng.randint(10, 120)))
        if ok(as2):
            h2 = rng.choice(meta["handlers"][tier2])
            asgs[-1]["ended_at"], asgs[-1]["end_reason"] = as2, "escalated"
            asgs.append(dict(team_id=tier2, assignee_id=h2, type="escalation", rule_id=None, assigned_at=as2,
                             ended_at=None, end_reason=None))
            E("assigned", as2, "staff", "tier2_pickup")
            t2 = min(max(60, int(lognorm(rng, 0.6 * res_t, 0.9))), 6 * res_t)
            res2 = max(as2 + M(15), bm(cal2, as2, t2))
            if ok(res2):
                dec = rng.choice(K.HANDOFF).format(team=ctx.teams[tier2]["team_name"], decision=rng.choice(K.DECISIONS))
                ans = _make_answer(ctx, p["policy"], p["fact"], res2, rng, intro=False) if outcome == "matched" else None
                if ans:
                    dec = dec + " " + ans["body"]
                MSG("handoff_response", res2, "staff", dec, ans)
                r_at = res2 + M(2)
                if ok(r_at):
                    E("resolved", r_at, "staff", "tier2_decision")
                    st["resolved"] = st["first_resolved"] = r_at

    # ---- optional reassignment inside the tier-1 in_progress window
    if p["reassign"]:
        first = asgs[0]
        stage_end = next((e["at"] for e in ev if e["type"] in ("clarification_requested", "escalated", "resolved", "closed")
                          and e["at"] > first["assigned_at"]), None)
        if stage_end and (stage_end - first["assigned_at"]).total_seconds() / 60 >= 12:
            span = int((stage_end - first["assigned_at"]).total_seconds() / 60) - 2
            tr = first["assigned_at"] + M(rng.randint(1, span))
            h1b = rng.choice([h for h in meta["handlers"][team1] if h != h1])
            old_end, old_reason = first["ended_at"], first["end_reason"]
            first["ended_at"], first["end_reason"] = tr, "reassigned"
            asgs.insert(1, dict(team_id=team1, assignee_id=h1b, type="reassignment", rule_id=None, assigned_at=tr,
                                ended_at=old_end, end_reason=old_reason))
            E("reassigned", tr, "staff", "staff_reassign")

    # ---- optional reopen (matched tickets only)
    if p["reopen"] and st["resolved"] and outcome == "matched":
        re_at = st["resolved"] + M(rng.randint(60, 5 * 1440))
        last = asgs[-1]
        calr = ctx.calendar_for(last["team_id"])
        as3 = max(re_at + M(3), bm(calr, re_at, rng.randint(2, 60)))
        ans3_at = max(as3 + M(10), bm(calr, as3, rng.randint(10, 240)))
        ans3 = _make_answer(ctx, p["policy"], p["fact"], ans3_at, rng)
        if ok(ans3_at + M(2)) and ans3:
            last["ended_at"], last["end_reason"] = st["resolved"], "resolved"
            MSG("reopen_request", re_at, "requester", rng.choice(K.REOPEN))
            E("reopened", re_at, "requester", "requester_reopened")
            asgs.append(dict(team_id=last["team_id"], assignee_id=last["assignee_id"], type="reopen", rule_id=None,
                             assigned_at=as3, ended_at=None, end_reason=None))
            E("assigned", as3, "staff", "reopen_pickup")
            MSG("answer", ans3_at, "staff", ans3["body"], ans3)
            st["resolved"] = ans3_at + M(2)
            E("resolved", st["resolved"], "staff", "policy_answer")

    if st["resolved"]:
        asgs[-1]["ended_at"], asgs[-1]["end_reason"] = st["resolved"], "resolved"
        close_at = st["resolved"] + timedelta(days=7)
        if ok(close_at):
            E("closed", close_at, "system", "auto_close_after_resolution")
            st["closed"] = True

    ev.sort(key=lambda e: e["at"])           # stable: equal timestamps keep generation order
    art_first = next((m["cites"][0] for m in msgs if m["cites"]), art0["article_id"] if art0 else None)
    tags = []
    if a > 0:
        tags.append("ambiguous")
    if outcome == "no_current_policy":
        tags.append("outdated_or_withdrawn_policy")
    if dl_hours is not None and dl_hours <= 24:
        tags.append("urgent_deadline")
    elif dl_hours is not None and dl_hours <= 72:
        tags.append("deadline_72h")
    if reasons:
        tags.append("requires_human_escalation")
    if art0 and art_first and art_first != art0["article_id"]:
        tags.append("version_changed_before_answer")
    if rule["precedence"] > 10:
        tags.append("conditional_routing_rule")
    ticket = dict(ticket_id=tid, requester_id=p["requester"], term_id=ctx.term_for(t0.date()), category_id=p["cat"],
                  priority=prio, channel=p["channel"], subject=subject, created_at=t0,
                  requester_deadline_at=p["deadline_at"])
    retrieval = dict(retrieval_id=f"RET-{tid}", ticket_id=tid, retrieved_at=t0 + M(1),
                     matched_policy_id=p["policy"], matched_article_id=art0["article_id"] if art0 else None,
                     initial_confidence=round(c_init, 3), final_confidence=round(c_fin, 3), outcome=outcome)
    truth = dict(ticket_id=tid, expected_team_id=team1, expected_priority=prio, expected_escalation=bool(reasons),
                 expected_escalation_reason=reasons[0] if reasons else None, expected_policy_id=p["policy"],
                 expected_article_id=art_first, case_tags="|".join(tags))
    return dict(ticket=ticket, retrieval=retrieval, msgs=msgs, events=ev, asgs=asgs, truth=truth,
                anomaly=None, team1=team1, tier2=tier2, prof=p, reasons=reasons, outcome=outcome)


def simulate(cfg: Config, t: dict, meta: dict, ctx: Context) -> list[dict]:
    profs = make_profiles(cfg, ctx, t, meta)
    return [build_bundle(i, p, ctx, meta, cfg) for i, p in enumerate(profs, 1)]
