"""Step 2a: parent / master tables (generated before any transaction)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from . import catalog as K
from .bizcal import CALENDAR_DEFS, HOLIDAYS_2026
from .config import Config, rng_for


def _rand_date(rng, lo: date, hi: date) -> date:
    return lo + timedelta(days=rng.randint(0, (hi - lo).days))


def build_master(cfg: Config):
    """Returns (tables, meta). `meta` holds sampling helpers that are NOT part of the dataset."""
    asof_d = cfg.as_of.date()
    t: dict[str, list[dict]] = {}

    t["role"] = [dict(role_id=r, role_name=n, role_group=g, can_file_tickets=f, can_resolve_tickets=s, description=d)
                 for r, n, g, f, s, d in K.ROLE_DEFS]

    terms = []
    for tid, name, s, e, ro in K.TERM_DEFS:
        sd, ed = date(*s), date(*e)
        status = "completed" if ed < asof_d else ("active" if sd <= asof_d else "upcoming")
        terms.append(dict(term_id=tid, term_name=name, start_date=sd, end_date=ed,
                          registration_open_date=date(*ro), status=status))
    t["term"] = terms

    t["business_calendar"] = [dict(calendar_id=c, name=n, timezone_label="campus-local") for c, n, _ in CALENDAR_DEFS]
    t["calendar_hours"] = [dict(hours_id=f"CH-{c}-{wd}", calendar_id=c, weekday=wd, open_minute=o, close_minute=cl)
                           for c, _, h in CALENDAR_DEFS for wd, (o, cl) in sorted(h.items())]
    t["holiday"] = [dict(holiday_id=f"HOL-{d:%Y%m%d}", holiday_date=d, name=n) for d, n in HOLIDAYS_2026]

    t["team"] = [dict(team_id=i, team_name=n, tier=tier, domain=dom, calendar_id=cal, escalation_team_id=esc, active=True)
                 for i, n, tier, dom, cal, esc in K.TEAM_DEFS]

    t["category"] = [dict(category_id=c[0], domain=c[1], domain_name=c[2], category_name=c[3], default_priority=c[4],
                          human_review_required=c[5], deadline_sensitive=c[6], description=c[8]) for c in K.CATEGORIES]

    auth, n = [], 0
    for c in K.CATEGORIES:
        owners = [K.DOMAIN_TEAM[c[1]]] + (["TEAM-PLATFORM"] if c[1] == "IT" else ["TEAM-ACADADM"])
        for team in owners:
            n += 1
            auth.append(dict(authorization_id=f"AUTH-{n:06d}", team_id=team, category_id=c[0],
                             effective_from=date(2025, 1, 1), effective_to=None))
    t["team_category_authorization"] = auth

    t["sla_policy"] = [dict(sla_policy_id=i, priority=p, first_response_minutes=fr, resolution_minutes=rs,
                            effective_from=date(2025, 1, 1), effective_to=None) for i, p, fr, rs in K.SLA_DEFS]

    rr = []
    for i, c in enumerate(K.CATEGORIES, 1):
        rr.append(dict(routing_rule_id=f"RR-{i:03d}", category_id=c[0], requester_role_id=None,
                       target_team_id=K.DOMAIN_TEAM[c[1]], priority_override=None, precedence=10,
                       effective_from=date(2025, 1, 1), effective_to=None,
                       description=f"Default: {c[3]} -> {K.DOMAIN_TEAM[c[1]]}"))
    nxt = len(rr) + 1
    rr.append(dict(routing_rule_id=f"RR-{nxt:03d}", category_id="CAT-IT-02", requester_role_id="ROLE-INSTRUCTOR",
                   target_team_id="TEAM-IT", priority_override="high", precedence=20,
                   effective_from=date(2025, 1, 1), effective_to=None,
                   description="Conditional: instructor LMS/course-access problems affect live classes -> high priority"))
    rr.append(dict(routing_rule_id=f"RR-{nxt + 1:03d}", category_id="CAT-REG-04", requester_role_id="ROLE-INSTRUCTOR",
                   target_team_id="TEAM-REG", priority_override="high", precedence=20,
                   effective_from=date(2025, 1, 1), effective_to=None,
                   description="Conditional: instructor grade-change petitions are prioritised"))
    t["routing_rule"] = rr

    # ------------------------------------------------------------------ people
    rng = rng_for(cfg.seed, "requesters")
    people, weights = [], {}
    counter = [0]

    def person(role_id, dept, team_id, af, at, level=None):
        counter[0] += 1
        n = counter[0]
        first, last = rng.choice(K.FIRST), rng.choice(K.LAST)
        status = "inactive" if (at and at <= asof_d) else "active"
        people.append(dict(requester_id=f"REQ-{n:06d}", role_id=role_id, full_name=f"{first} {last}",
                           email=f"{first}.{last}.{n}@campus.example.edu".lower(), department_code=dept,
                           program_level=level, team_id=team_id, status=status, active_from=af, active_to=at))
        weights[f"REQ-{n:06d}"] = min(30.0, rng.paretovariate(1.6))

    for _ in range(cfg.n_learners):
        af = _rand_date(rng, date(2022, 8, 22), date(2026, 6, 30) if rng.random() < 0.95 else date(2026, 8, 24))
        at = _rand_date(rng, date(2026, 2, 1), date(2026, 10, 15)) if rng.random() < 0.08 else None
        lvl = rng.choices(["undergraduate", "graduate", "non_degree"], [70, 25, 5])[0]
        person("ROLE-LEARNER", rng.choice(K.DEPTS), None, af, at, lvl)
    for _ in range(cfg.n_instructors):
        af = _rand_date(rng, date(2008, 8, 1), date(2025, 8, 1))
        at = _rand_date(rng, date(2026, 3, 1), date(2026, 9, 30)) if rng.random() < 0.03 else None
        person("ROLE-INSTRUCTOR", rng.choice(K.DEPTS), None, af, at)
    for _ in range(cfg.n_acad_admin_requesters):
        person("ROLE-ACADADMIN", "ADM", None, _rand_date(rng, date(2010, 8, 1), date(2024, 8, 1)), None)
    handlers = {}
    for team_id, *_ in K.TEAM_DEFS:
        k = cfg.staff_per_tier1_team if team_id in K.DOMAIN_TEAM.values() else (5 if team_id == "TEAM-ACADADM" else 4)
        role = {"TEAM-ACADADM": "ROLE-ACADADMIN", "TEAM-PLATFORM": "ROLE-PLATADMIN"}.get(team_id, "ROLE-SUPPORT")
        ids = []
        for _ in range(k):
            person(role, K.TEAM_DEPT[team_id], team_id, _rand_date(rng, date(2015, 8, 1), date(2024, 8, 1)), None)
            ids.append(people[-1]["requester_id"])
        handlers[team_id] = ids
    t["requester"] = people

    # ------------------------------------------------------------------ policies / articles
    prng = rng_for(cfg.seed, "policies")
    P, A = cfg.policies, cfg.articles
    per_cat = [P // 16 + (1 if i < P % 16 else 0) for i in range(16)]
    pols, dom_counter = [], {d: 0 for d in ("FIN", "REG", "IT", "ACC")}
    for ci, c in enumerate(K.CATEGORIES):
        for j in range(per_cat[ci]):
            dom_counter[c[1]] += 1
            pols.append(dict(policy_id=f"POL-{c[1]}-2026-{dom_counter[c[1]]:03d}", cat=c, j=j))
    base, rem = divmod(A, P)
    nver = [base] * P
    for idx in prng.sample(range(P), rem):
        nver[idx] += 1
    for _ in range(P):
        a, b = prng.sample(range(P), 2)
        if nver[a] > 2 and nver[b] < 7:
            nver[a] -= 1
            nver[b] += 1
    retired, used_cats = {}, set()
    order = list(range(P))
    prng.shuffle(order)
    for idx in order:
        if len(retired) >= max(1, round(P * 0.085)):
            break
        cid = pols[idx]["cat"][0]
        if cid not in used_cats:
            used_cats.add(cid)
            retired[pols[idx]["policy_id"]] = _rand_date(prng, date(2026, 3, 1), date(2026, 7, 15))

    policy_rows, art_rows, fact_rows, ac_rows = [], [], [], []
    kb_n = fact_n = ac_n = 0
    for pi, p in enumerate(pols):
        cat, j, pid = p["cat"], p["j"], p["policy_id"]
        facts_def = [cat[9][j % 3], cat[9][(j + 1) % 3]]
        n_v = nver[pi]
        last_start = (_rand_date(prng, date(2026, 2, 1), date(2026, 8, 15))
                      if (pid not in retired and prng.random() < 0.40)
                      else _rand_date(prng, date(2025, 3, 1), date(2026, 1, 2)))
        starts = [last_start]
        for _ in range(n_v - 1):
            starts.insert(0, starts[0] - timedelta(days=prng.randint(120, 420)))
        title = f"{cat[3]}: {K.VARIANTS[j % len(K.VARIANTS)]}"
        owner = K.DOMAIN_TEAM[cat[1]]
        vals = [prng.choice(fd[4]) for fd in facts_def]
        prev_id = None
        sec_cats = [c2[0] for c2 in K.CATEGORIES if c2[1] == cat[1] and c2[0] != cat[0]]
        for k in range(n_v):
            if k > 0:
                new = list(vals)
                for fi, fd in enumerate(facts_def):
                    if prng.random() < 0.5:
                        new[fi] = prng.choice([x for x in fd[4] if x != vals[fi]])
                if new == vals:
                    new[0] = prng.choice([x for x in facts_def[0][4] if x != vals[0]])
                vals = new
            kb_n += 1
            aid = f"KB-{kb_n:06d}"
            eff_from = starts[k]
            eff_to = (starts[k + 1] - timedelta(days=1)) if k < n_v - 1 else (
                retired[pid] - timedelta(days=1) if pid in retired else None)
            if eff_to is None or eff_to >= asof_d:
                status = "current" if eff_from <= asof_d else "superseded"
            else:
                status = "superseded" if k < n_v - 1 else "retired"
            sentences = [fd[2].format(v=v) for fd, v in zip(facts_def, vals)]
            body = (f"{title} (version {k + 1}). Effective {eff_from.isoformat()}. " + " ".join(sentences)
                    + " Exceptions require written approval from the owning office.")
            pub = datetime.combine(eff_from - timedelta(days=prng.randint(5, 30)), time(9, 0)) \
                + timedelta(minutes=prng.randint(0, 300))
            art_rows.append(dict(article_id=aid, policy_id=pid, version_no=k + 1, title=title, body=body,
                                 effective_from=eff_from, effective_to=eff_to, status=status,
                                 supersedes_article_id=prev_id, author_id=prng.choice(handlers[owner]),
                                 published_at=pub))
            for fd, v in zip(facts_def, vals):
                fact_n += 1
                fact_rows.append(dict(fact_id=f"FACT-{fact_n:06d}", article_id=aid, fact_key=fd[0],
                                      fact_value=str(v), unit=fd[3] or None))
            ac_n += 1
            ac_rows.append(dict(article_category_id=f"AC-{ac_n:06d}", article_id=aid, category_id=cat[0], is_primary=True))
            if prng.random() < 0.4:
                ac_n += 1
                ac_rows.append(dict(article_category_id=f"AC-{ac_n:06d}", article_id=aid,
                                    category_id=prng.choice(sec_cats), is_primary=False))
            prev_id = aid
        policy_rows.append(dict(policy_id=pid, domain=cat[1], title=title, category_id=cat[0], owner_team_id=owner,
                                status="retired" if pid in retired else "active", first_effective_date=starts[0],
                                retired_date=retired.get(pid), is_synthetic=True,
                                source_note="Synthetic policy authored by the generator; no external source or PII."))
    t["policy_document"], t["knowledge_article"] = policy_rows, art_rows
    t["article_fact"], t["article_category"] = fact_rows, ac_rows

    meta = dict(req_weight=weights, handlers=handlers, retired=retired)
    return t, meta
