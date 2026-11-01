"""Documented business rules (see docs/RULES.md). Used by the generator to decide outcomes AND by the
evaluator to re-derive expectations from input tables only, so rules live in exactly one place."""
from __future__ import annotations

from datetime import date, datetime

from . import catalog as K
from .bizcal import Calendar, add_business_minutes, business_minutes_between, calendar_24x7
from .schema import PRIORITIES

CONF_CLARIFY = 0.70          # initial confidence below this -> ask clarification (max 2 rounds)
CONF_LOW = 0.45              # final confidence below this -> ambiguity_unresolved escalation (E3)
DEADLINE_URGENT_HOURS = 24   # deadline within this -> urgent priority / E4 on deadline-sensitive categories
DEADLINE_SOON_HOURS = 72     # deadline within this -> priority bumped one level
NO_REPLY_WAIT_MINUTES = 960  # business minutes to wait for a clarification reply before escalating (E3)
STALL_CLOSE_MINUTES = 6720   # business minutes (14 business days, std calendar) before no-response auto-close

FACT_BY_KEY = {f[0]: f for c in K.CATEGORIES for f in c[9]}


class Context:
    """Read-only view over master/rule tables with typed (native) values."""

    def __init__(self, t: dict, as_of: datetime):
        self.as_of = as_of
        self.categories = {r["category_id"]: r for r in t["category"]}
        self.teams = {r["team_id"]: r for r in t["team"]}
        self.roles = {r["role_id"]: r for r in t["role"]}
        self.requesters = {r["requester_id"]: r for r in t["requester"]}
        self.terms = sorted(t["term"], key=lambda r: r["start_date"])
        holidays = frozenset(r["holiday_date"] for r in t["holiday"])
        hours: dict[str, dict] = {}
        for r in t["calendar_hours"]:
            hours.setdefault(r["calendar_id"], {})[r["weekday"]] = (r["open_minute"], r["close_minute"])
        self.calendars = {c["calendar_id"]: Calendar(c["calendar_id"], hours.get(c["calendar_id"], {}), holidays)
                          for c in t["business_calendar"]}
        self.cal24 = calendar_24x7()
        self.sla_by_priority = {r["priority"]: r for r in t["sla_policy"]}
        self.sla_policies = {r["sla_policy_id"]: r for r in t["sla_policy"]}
        self.rules = t["routing_rule"]
        self.auth = {}
        for r in t["team_category_authorization"]:
            self.auth.setdefault((r["team_id"], r["category_id"]), []).append(r)
        self.policies = {r["policy_id"]: r for r in t["policy_document"]}
        self.articles = {r["article_id"]: r for r in t["knowledge_article"]}
        self.versions: dict[str, list] = {}
        for r in sorted(t["knowledge_article"], key=lambda r: (r["policy_id"], r["version_no"])):
            self.versions.setdefault(r["policy_id"], []).append(r)
        self.facts: dict[str, dict] = {}
        for r in t["article_fact"]:
            self.facts.setdefault(r["article_id"], {})[r["fact_key"]] = r["fact_value"]
        self.policies_by_category: dict[str, list] = {}
        for r in t["policy_document"]:
            self.policies_by_category.setdefault(r["category_id"], []).append(r["policy_id"])

    # ---- calendars
    def calendar_for(self, team_id: str) -> Calendar:
        return self.calendars[self.teams[team_id]["calendar_id"]]

    # ---- terms
    def term_for(self, d: date) -> str:
        for tm in self.terms:
            if d <= tm["end_date"]:
                return tm["term_id"]
        return self.terms[-1]["term_id"]

    # ---- R1 routing
    def route(self, category_id: str, role_id: str, on: date):
        best = None
        for r in self.rules:
            if r["category_id"] != category_id:
                continue
            if r["requester_role_id"] not in (None, role_id):
                continue
            if r["effective_from"] > on or (r["effective_to"] and r["effective_to"] < on):
                continue
            if best is None or r["precedence"] > best["precedence"]:
                best = r
        return best

    def is_authorized(self, team_id: str, category_id: str, on: date) -> bool:
        return any(a["effective_from"] <= on and (a["effective_to"] is None or a["effective_to"] >= on)
                   for a in self.auth.get((team_id, category_id), []))

    # ---- P1 priority
    def priority(self, category_id: str, deadline_hours, rule) -> str:
        lvl = PRIORITIES.index(self.categories[category_id]["default_priority"])
        if deadline_hours is not None:
            if deadline_hours <= DEADLINE_URGENT_HOURS:
                lvl = 3
            elif deadline_hours <= DEADLINE_SOON_HOURS:
                lvl = min(3, lvl + 1)
        if rule is not None and rule["priority_override"]:
            lvl = max(lvl, PRIORITIES.index(rule["priority_override"]))
        return PRIORITIES[lvl]

    # ---- K1 knowledge versions
    def effective_article(self, policy_id: str, on: date):
        for a in self.versions.get(policy_id, []):
            if a["effective_from"] <= on and (a["effective_to"] is None or a["effective_to"] >= on):
                return a
        return None

    # ---- retrieval outcome + E1..E4 escalation
    @staticmethod
    def retrieval_outcome(has_current_article: bool, final_confidence: float) -> str:
        if not has_current_article:
            return "no_current_policy"
        return "low_confidence" if final_confidence < CONF_LOW else "matched"

    def escalation_reasons(self, category_id: str, outcome: str, deadline_hours) -> list:
        cat = self.categories[category_id]
        out = []
        if cat["human_review_required"]:
            out.append("human_review_required")                       # E1
        if outcome == "no_current_policy":
            out.append("no_current_policy")                           # E2
        if outcome == "low_confidence":
            out.append("ambiguity_unresolved")                        # E3
        if cat["deadline_sensitive"] and deadline_hours is not None and deadline_hours <= DEADLINE_URGENT_HOURS:
            out.append("urgent_deadline")                             # E4
        return out

    # ---- S1 SLA
    def sla_times(self, calendar: Calendar, start: datetime, priority: str):
        p = self.sla_by_priority[priority]
        return (p, add_business_minutes(calendar, start, p["first_response_minutes"]),
                add_business_minutes(calendar, start, p["resolution_minutes"]))

    @staticmethod
    def elapsed(calendar: Calendar, a: datetime, b: datetime) -> int:
        return business_minutes_between(calendar, a, b)
