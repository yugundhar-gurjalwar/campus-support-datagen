"""Single source of truth: tables, columns, enums, relationships, lifecycle.
Drives the data dictionary, SQL DDL, structural validation and exports."""
from __future__ import annotations

from dataclasses import dataclass

# ----------------------------------------------------------------------------- enums
PRIORITIES = ("low", "normal", "high", "urgent")
STATUSES = ("new", "triaged", "in_progress", "pending_requester", "escalated",
            "resolved", "reopened", "closed")
EVENT_TYPES = ("created", "routed", "assigned", "clarification_requested",
               "clarification_received", "escalated", "reassigned", "resolved",
               "reopened", "closed")
MSG_TYPES = ("question", "system_ack", "clarification_request", "clarification_reply",
             "answer", "agent_update", "escalation_note", "handoff_response",
             "requester_followup", "reopen_request", "thanks")
SENDER_TYPES = ("requester", "support_staff", "system")
CHANNELS = ("portal", "email", "chat", "phone")
DOMAINS = ("FIN", "REG", "IT", "ACC")
DOMAIN_NAMES = ("financial_aid", "registration", "it", "accessibility")
ESC_REASONS = ("human_review_required", "no_current_policy", "ambiguity_unresolved", "urgent_deadline")
REASON_CODES = ESC_REASONS + ("routing_rule", "initial_pickup", "tier2_pickup", "reopen_pickup",
                              "staff_reassign", "policy_answer", "tier2_decision",
                              "requester_reopened", "no_response", "auto_close_after_resolution",
                              "needs_clarification", "clarification_provided")
RESOLUTION_CODES = ("answered_by_policy", "resolved_after_escalation", "closed_no_response")
ISSUE_TYPES = ("answer_cites_expired_policy", "ticket_routed_to_unauthorized_team",
               "response_claims_unsupported_fact", "sla_clock_ignores_business_hours",
               "escalation_not_triggered")
COMMENT_CODES = ("fast_and_clear", "helpful", "slow", "unclear", "wrong_or_outdated", "unresolved", "none")

# Allowed (from_status, event_type) -> to_status. None = ticket does not exist yet.
TRANSITIONS = {
    (None, "created"): "new",
    ("new", "routed"): "triaged",
    ("triaged", "assigned"): "in_progress",
    ("in_progress", "clarification_requested"): "pending_requester",
    ("pending_requester", "clarification_received"): "in_progress",
    ("in_progress", "escalated"): "escalated",
    ("pending_requester", "escalated"): "escalated",
    ("escalated", "assigned"): "in_progress",
    ("in_progress", "reassigned"): "in_progress",
    ("in_progress", "resolved"): "resolved",
    ("pending_requester", "closed"): "closed",
    ("resolved", "closed"): "closed",
    ("resolved", "reopened"): "reopened",
    ("reopened", "assigned"): "in_progress",
}

# ----------------------------------------------------------------------------- model
@dataclass(frozen=True)
class Col:
    name: str
    typ: str                      # str | text | int | float | bool | date | datetime
    req: bool = True
    enum: tuple | None = None
    fk: str | None = None         # "table.column"
    unique: bool = False
    unit: str = ""
    rule: str = ""
    pattern: str | None = None
    lo: float | None = None
    hi: float | None = None


@dataclass(frozen=True)
class Table:
    name: str
    pk: str
    kind: str                     # master | bridge | event | transaction | derived
    desc: str
    cols: tuple
    unique_together: tuple = ()
    cardinality: str = ""


def C(name, typ="str", req=True, **kw):
    return Col(name, typ, req, **kw)


TABLES: list[Table] = [
    Table("role", "role_id", "master", "Actor roles recognised by the platform.", (
        C("role_id", pattern=r"^ROLE-[A-Z]+$", unique=True, rule="immutable"),
        C("role_name", enum=("Learner", "Instructor", "Academic Administrator", "Support Staff", "Platform Administrator"), unique=True),
        C("role_group", enum=("requester", "staff", "admin")),
        C("can_file_tickets", "bool"), C("can_resolve_tickets", "bool"),
        C("description", "text")), cardinality="Role 1:N Requester"),
    Table("term", "term_id", "master", "Academic terms; ticket.term_id is the term in session (or next term during breaks) at creation.", (
        C("term_id", pattern=r"^TERM-\d{4}-(SP|SU|FA)$", unique=True),
        C("term_name"), C("start_date", "date"), C("end_date", "date", rule="end_date > start_date"),
        C("registration_open_date", "date", rule="<= start_date"),
        C("status", enum=("completed", "active", "upcoming"), rule="derived from dataset as_of date")),
        cardinality="Term 1:N Ticket"),
    Table("business_calendar", "calendar_id", "master", "Named business-hours calendars used by SLA clocks.", (
        C("calendar_id", pattern=r"^CAL-[A-Z0-9]+$", unique=True), C("name"),
        C("timezone_label", enum=("campus-local",), rule="all timestamps are naive campus-local time")),
        cardinality="Calendar 1:N CalendarHours; Calendar 1:N Team; Calendar 1:N SLA"),
    Table("calendar_hours", "hours_id", "master", "Open window per weekday for a calendar (absent weekday = closed).", (
        C("hours_id", pattern=r"^CH-CAL-[A-Z0-9]+-\d$", unique=True),
        C("calendar_id", fk="business_calendar.calendar_id"),
        C("weekday", "int", lo=0, hi=6, rule="Mon=0"),
        C("open_minute", "int", unit="minutes after midnight", lo=0, hi=1440),
        C("close_minute", "int", unit="minutes after midnight", lo=0, hi=1440, rule="> open_minute")),
        unique_together=(("calendar_id", "weekday"),)),
    Table("holiday", "holiday_id", "master", "Campus closures; no business minutes accrue on these dates.", (
        C("holiday_id", pattern=r"^HOL-\d{8}$", unique=True), C("holiday_date", "date", unique=True), C("name"))),
    Table("team", "team_id", "master", "Support teams. Tier 1 = domain desks; tier 2 = escalation teams.", (
        C("team_id", pattern=r"^TEAM-[A-Z]+$", unique=True), C("team_name"),
        C("tier", "int", lo=1, hi=2), C("domain", enum=DOMAINS + ("ADMIN", "PLAT")),
        C("calendar_id", fk="business_calendar.calendar_id"),
        C("escalation_team_id", req=False, fk="team.team_id", rule="tier-1 teams only; must be tier 2"),
        C("active", "bool")), cardinality="Team 1:N Requester(staff); Team 1:N Assignment; Team 1:0..1 EscalationTeam"),
    Table("requester", "requester_id", "master", "Every person in the system (ticket requesters and staff/admin handlers). Synthetic identities only.", (
        C("requester_id", pattern=r"^REQ-\d{6}$", unique=True),
        C("role_id", fk="role.role_id"), C("full_name"),
        C("email", unique=True, pattern=r"^[a-z0-9._-]+@campus\.example\.edu$", rule="reserved example domain; no real PII"),
        C("department_code", enum=("CS", "BUS", "NUR", "ENG", "ART", "BIO", "FAO", "REGO", "ITS", "DSS", "ADM")),
        C("program_level", req=False, enum=("undergraduate", "graduate", "non_degree"), rule="learners only"),
        C("team_id", req=False, fk="team.team_id", rule="set iff role is Support Staff / Academic Admin / Platform Admin handler"),
        C("status", enum=("active", "inactive")),
        C("active_from", "date"), C("active_to", "date", req=False, rule=">= active_from; null = still active")),
        cardinality="Requester 1:N Ticket; Requester(staff) 1:N Assignment"),
    Table("category", "category_id", "master", "Request categories (4 domains x 4 sub-topics).", (
        C("category_id", pattern=r"^CAT-(FIN|REG|IT|ACC)-\d{2}$", unique=True),
        C("domain", enum=DOMAINS), C("domain_name", enum=DOMAIN_NAMES), C("category_name"),
        C("default_priority", enum=PRIORITIES),
        C("human_review_required", "bool", rule="escalation rule E1: always needs a tier-2 decision"),
        C("deadline_sensitive", "bool", rule="escalation rule E4 applies when a deadline is <= 24h away"),
        C("description", "text")), cardinality="Category 1:N Ticket; Category N:M Team; Category N:M Article"),
    Table("team_category_authorization", "authorization_id", "bridge", "Which team may legitimately handle which category (N:M bridge).", (
        C("authorization_id", pattern=r"^AUTH-\d{6}$", unique=True),
        C("team_id", fk="team.team_id"), C("category_id", fk="category.category_id"),
        C("effective_from", "date"), C("effective_to", "date", req=False)),
        unique_together=(("team_id", "category_id"),), cardinality="Team N:M Category"),
    Table("sla_policy", "sla_policy_id", "master", "SLA targets per priority, measured in business minutes of the handling team's calendar.", (
        C("sla_policy_id", pattern=r"^SLAP-[A-Z]+$", unique=True),
        C("priority", enum=PRIORITIES, unique=True),
        C("first_response_minutes", "int", unit="business minutes", lo=1),
        C("resolution_minutes", "int", unit="business minutes", lo=1, rule="> first_response_minutes"),
        C("effective_from", "date"), C("effective_to", "date", req=False)),
        cardinality="SlaPolicy 1:N SLA"),
    Table("routing_rule", "routing_rule_id", "master", "Routing rules; highest precedence matching rule wins.", (
        C("routing_rule_id", pattern=r"^RR-\d{3}$", unique=True),
        C("category_id", fk="category.category_id"),
        C("requester_role_id", req=False, fk="role.role_id", rule="null = any role (generic rule)"),
        C("target_team_id", fk="team.team_id", rule="team must be authorised for category_id"),
        C("priority_override", req=False, enum=PRIORITIES),
        C("precedence", "int", lo=1), C("effective_from", "date"), C("effective_to", "date", req=False),
        C("description", "text")), cardinality="Category 1:N RoutingRule; RoutingRule 0..N:1 Assignment"),
    Table("policy_document", "policy_id", "master", "Policy documents (synthetic). Each has 1..N dated versions held as knowledge articles.", (
        C("policy_id", pattern=r"^POL-(FIN|REG|IT|ACC)-2026-\d{3}$", unique=True),
        C("domain", enum=DOMAINS), C("title"),
        C("category_id", fk="category.category_id"), C("owner_team_id", fk="team.team_id"),
        C("status", enum=("active", "retired"), rule="derived: retired iff newest version expired before as_of"),
        C("first_effective_date", "date"), C("retired_date", "date", req=False),
        C("is_synthetic", "bool", rule="always true: no external data used"),
        C("source_note", "text")), cardinality="PolicyDocument 1:N KnowledgeArticle (versions)"),
    Table("knowledge_article", "article_id", "master", "One published VERSION of a policy document, with effective dates.", (
        C("article_id", pattern=r"^KB-\d{6}$", unique=True),
        C("policy_id", fk="policy_document.policy_id"),
        C("version_no", "int", lo=1, rule="contiguous 1..N per policy"),
        C("title"), C("body", "text"),
        C("effective_from", "date"),
        C("effective_to", "date", req=False, rule="inclusive; = next version effective_from - 1 day; null = open-ended"),
        C("status", enum=("current", "superseded", "retired"), rule="derived relative to as_of"),
        C("supersedes_article_id", req=False, fk="knowledge_article.article_id", rule="previous version of same policy"),
        C("author_id", fk="requester.requester_id"), C("published_at", "datetime", rule="<= effective_from + 0d")),
        unique_together=(("policy_id", "version_no"),), cardinality="Article 1:N ArticleFact; Article N:M Category; Article N:M Message"),
    Table("article_fact", "fact_id", "master", "Machine-checkable facts stated by an article version (used to verify claims).", (
        C("fact_id", pattern=r"^FACT-\d{6}$", unique=True),
        C("article_id", fk="knowledge_article.article_id"), C("fact_key"), C("fact_value"),
        C("unit", req=False)), unique_together=(("article_id", "fact_key"),)),
    Table("article_category", "article_category_id", "bridge", "Article <-> category applicability (N:M bridge).", (
        C("article_category_id", pattern=r"^AC-\d{6}$", unique=True),
        C("article_id", fk="knowledge_article.article_id"), C("category_id", fk="category.category_id"),
        C("is_primary", "bool")), unique_together=(("article_id", "category_id"),), cardinality="Article N:M Category"),
    Table("ticket", "ticket_id", "transaction", "A support request. Intake fields are inputs; status/current_team_id/resolved_at/closed_at/resolution_code/*_count are DERIVED from event, assignment and message records.", (
        C("ticket_id", pattern=r"^TKT-2026-\d{6}$", unique=True),
        C("requester_id", fk="requester.requester_id", rule="requester role must be able to file tickets and be active at created_at"),
        C("term_id", fk="term.term_id"), C("category_id", fk="category.category_id"),
        C("priority", enum=PRIORITIES, rule="output of priority rule P1 at creation"),
        C("channel", enum=CHANNELS), C("subject"),
        C("created_at", "datetime", unit="campus-local minute"),
        C("requester_deadline_at", "datetime", req=False, rule="requester-stated deadline; > created_at"),
        C("status", enum=STATUSES, rule="= to_status of last ticket_event"),
        C("current_team_id", req=False, fk="team.team_id", rule="team of the open assignment; null when none open"),
        C("resolved_at", "datetime", req=False, rule="time of last 'resolved' event"),
        C("closed_at", "datetime", req=False), C("resolution_code", req=False, enum=RESOLUTION_CODES),
        C("reopen_count", "int", lo=0, rule="= count of 'reopened' events"),
        C("escalation_count", "int", lo=0, rule="= count of 'escalated' events"),
        C("message_count", "int", lo=1, rule="= count of message rows")),
        cardinality="Ticket 1:N Event/Message/Assignment; Ticket 1:1 SLA; Ticket 1:1 RetrievalResult; Ticket 1:0..1 Feedback"),
    Table("ticket_event", "event_id", "event", "Append-only lifecycle history; one row per state change. Never updated.", (
        C("event_id", pattern=r"^EVT-TKT-2026-\d{6}-\d{3}$", unique=True),
        C("ticket_id", fk="ticket.ticket_id"), C("event_seq", "int", lo=1, rule="contiguous per ticket"),
        C("event_type", enum=EVENT_TYPES), C("from_status", req=False, enum=STATUSES),
        C("to_status", enum=STATUSES, rule="must equal TRANSITIONS[(from_status, event_type)]"),
        C("event_at", "datetime", rule="non-decreasing in event_seq"),
        C("actor_type", enum=SENDER_TYPES), C("actor_id", req=False, fk="requester.requester_id"),
        C("team_id", req=False, fk="team.team_id"), C("reason_code", req=False, enum=REASON_CODES)),
        unique_together=(("ticket_id", "event_seq"),)),
    Table("retrieval_result", "retrieval_id", "transaction", "Outcome of the policy-retrieval step run when the ticket is routed.", (
        C("retrieval_id", pattern=r"^RET-TKT-2026-\d{6}$", unique=True),
        C("ticket_id", fk="ticket.ticket_id", unique=True), C("retrieved_at", "datetime"),
        C("matched_policy_id", req=False, fk="policy_document.policy_id"),
        C("matched_article_id", req=False, fk="knowledge_article.article_id", rule="version effective at retrieved_at; null if none"),
        C("initial_confidence", "float", lo=0, hi=1), C("final_confidence", "float", lo=0, hi=1, rule="after clarification rounds"),
        C("outcome", enum=("matched", "low_confidence", "no_current_policy"),
          rule="no_current_policy if no article effective; else low_confidence if final_confidence < 0.45; else matched")),
        cardinality="Ticket 1:1 RetrievalResult"),
    Table("message", "message_id", "event", "Conversation history. Append-only.", (
        C("message_id", pattern=r"^MSG-TKT-2026-\d{6}-\d{3}$", unique=True),
        C("ticket_id", fk="ticket.ticket_id"), C("message_seq", "int", lo=1, rule="contiguous per ticket; id suffix = seq"),
        C("sender_type", enum=SENDER_TYPES), C("sender_id", req=False, fk="requester.requester_id", rule="null iff system"),
        C("message_type", enum=MSG_TYPES), C("sent_at", "datetime", rule=">= ticket.created_at; non-decreasing in seq"),
        C("body", "text")), unique_together=(("ticket_id", "message_seq"),)),
    Table("message_citation", "citation_id", "bridge", "Message <-> article version cited (N:M bridge). Records the version cited.", (
        C("citation_id", pattern=r"^CIT-\d{6}$", unique=True),
        C("message_id", fk="message.message_id"), C("article_id", fk="knowledge_article.article_id"),
        C("article_version_no", "int", lo=1, rule="must equal knowledge_article.version_no"),
        C("citation_rank", "int", lo=1)), unique_together=(("message_id", "article_id"),), cardinality="Message N:M Article"),
    Table("message_claim", "claim_id", "event", "Verifiable factual statements made in a message.", (
        C("claim_id", pattern=r"^CLM-\d{6}$", unique=True),
        C("message_id", fk="message.message_id"), C("fact_key"), C("claimed_value"),
        C("supporting_article_id", req=False, fk="knowledge_article.article_id", rule="null = no supporting source")),
        cardinality="Message 1:N Claim"),
    Table("assignment", "assignment_id", "event", "Who handled the ticket and when; closed, never overwritten.", (
        C("assignment_id", pattern=r"^ASG-TKT-2026-\d{6}-\d{2}$", unique=True),
        C("ticket_id", fk="ticket.ticket_id"), C("assignment_seq", "int", lo=1),
        C("team_id", fk="team.team_id"), C("assignee_id", fk="requester.requester_id", rule="assignee.team_id must equal team_id"),
        C("assignment_type", enum=("initial", "reassignment", "escalation", "reopen")),
        C("routing_rule_id", req=False, fk="routing_rule.routing_rule_id", rule="set on 'initial' only"),
        C("assigned_at", "datetime"), C("ended_at", "datetime", req=False, rule=">= assigned_at"),
        C("end_reason", req=False, enum=("escalated", "reassigned", "resolved"))),
        unique_together=(("ticket_id", "assignment_seq"),)),
    Table("sla", "sla_id", "derived", "SLA clock per ticket. Due dates/elapsed/breach flags are computed from calendar + events + messages.", (
        C("sla_id", pattern=r"^SLA-TKT-2026-\d{6}$", unique=True),
        C("ticket_id", fk="ticket.ticket_id", unique=True),
        C("sla_policy_id", fk="sla_policy.sla_policy_id"), C("calendar_id", fk="business_calendar.calendar_id"),
        C("calendar_mode", enum=("business_hours", "calendar_24x7"), rule="must be business_hours"),
        C("clock_start_at", "datetime", rule="= ticket.created_at"),
        C("first_response_due_at", "datetime"), C("resolution_due_at", "datetime"),
        C("first_response_at", "datetime", req=False, rule="first support_staff message"),
        C("first_resolved_at", "datetime", req=False, rule="first 'resolved' event"),
        C("resolution_clock_stop_at", "datetime", rule="first_resolved_at, else closed_at, else dataset as_of"),
        C("first_response_elapsed_minutes", "int", req=False, unit="minutes (per calendar_mode)"),
        C("resolution_elapsed_minutes", "int", unit="minutes (per calendar_mode)"),
        C("first_response_breached", "bool"), C("resolution_breached", "bool")),
        cardinality="Ticket 1:1 SLA"),
    Table("resolution_feedback", "feedback_id", "event", "Requester feedback after resolution (optional; ~half of resolved tickets).", (
        C("feedback_id", pattern=r"^FB-TKT-2026-\d{6}$", unique=True),
        C("ticket_id", fk="ticket.ticket_id", unique=True), C("submitted_at", "datetime", rule="> last resolved event"),
        C("rating", "int", lo=1, hi=5, rule="rule score from SLA breaches/reopen, +/-1 noise on ~25%"),
        C("issue_resolved", "bool", rule="false iff ticket was reopened"),
        C("comment_code", enum=COMMENT_CODES)), cardinality="Ticket 1:0..1 Feedback"),
]

TABLE_MAP = {t.name: t for t in TABLES}
TABLE_ORDER = [t.name for t in TABLES]        # parents before children

GROUND_TRUTH_FILES = ("ground_truth_expected", "ground_truth_anomalies")
FORBIDDEN_INPUT_COLUMNS = {"issue_type", "ground_truth", "expected_team_id", "expected_priority",
                           "expected_escalation", "expected_escalation_reason", "expected_article_id",
                           "expected_policy_id", "case_tags", "injected"}

# ----------------------------------------------------------------------------- DDL
_SQL = {"str": "TEXT", "text": "TEXT", "date": "TEXT", "datetime": "TEXT",
        "int": "INTEGER", "bool": "INTEGER", "float": "REAL"}


def _lit(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


def ddl() -> str:
    out = ["-- Generated from campus_support.schema. SQLite/ANSI compatible.",
           "-- Dates are ISO-8601 TEXT; booleans are 0/1.", "PRAGMA foreign_keys = ON;", ""]
    for t in TABLES:
        lines = []
        for c in t.cols:
            parts = [f'"{c.name}"', _SQL[c.typ]]
            if c.name == t.pk:
                parts.append("PRIMARY KEY")
            elif c.req:
                parts.append("NOT NULL")
            if c.unique and c.name != t.pk:
                parts.append("UNIQUE")
            if c.typ == "bool":
                parts.append(f'CHECK ("{c.name}" IN (0,1))')
            if c.enum:
                parts.append(f'CHECK ("{c.name}" IN ({", ".join(_lit(e) for e in c.enum)}))')
            if c.lo is not None:
                parts.append(f'CHECK ("{c.name}" >= {c.lo})')
            if c.hi is not None:
                parts.append(f'CHECK ("{c.name}" <= {c.hi})')
            lines.append("  " + " ".join(parts))
        for c in t.cols:
            if c.fk:
                pt, pc = c.fk.split(".")
                lines.append(f'  FOREIGN KEY ("{c.name}") REFERENCES "{pt}" ("{pc}")')
        for ut in t.unique_together:
            lines.append("  UNIQUE (" + ", ".join(f'"{u}"' for u in ut) + ")")
        out.append(f'CREATE TABLE "{t.name}" (\n' + ",\n".join(lines) + "\n);\n")
    return "\n".join(out)


# ----------------------------------------------------------------------------- docs
RELATIONSHIPS = [
    ("role", "requester", "1:N", "required"), ("team", "requester", "1:N", "optional (staff only)"),
    ("business_calendar", "calendar_hours", "1:N", "required"), ("business_calendar", "team", "1:N", "required"),
    ("team", "team", "1:0..1", "optional (tier-1 -> tier-2 escalation team)"),
    ("team", "team_category_authorization", "1:N", "required"), ("category", "team_category_authorization", "1:N", "required"),
    ("category", "routing_rule", "1:N", "required"), ("role", "routing_rule", "1:N", "optional (conditional rule)"),
    ("team", "routing_rule", "1:N", "required"),
    ("category", "policy_document", "1:N", "required"), ("team", "policy_document", "1:N", "required"),
    ("policy_document", "knowledge_article", "1:N", "required (versions)"),
    ("knowledge_article", "article_fact", "1:N", "required"),
    ("knowledge_article", "article_category", "1:N", "required"), ("category", "article_category", "1:N", "required"),
    ("requester", "ticket", "1:N", "required"), ("term", "ticket", "1:N", "required"), ("category", "ticket", "1:N", "required"),
    ("ticket", "ticket_event", "1:N", "required"), ("ticket", "message", "1:N", "required"),
    ("ticket", "assignment", "1:N", "required"), ("ticket", "sla", "1:1", "required"),
    ("sla_policy", "sla", "1:N", "required"), ("ticket", "retrieval_result", "1:1", "required"),
    ("ticket", "resolution_feedback", "1:0..1", "optional"),
    ("message", "message_citation", "1:N", "optional"), ("knowledge_article", "message_citation", "1:N", "optional"),
    ("message", "message_claim", "1:N", "optional"), ("knowledge_article", "message_claim", "1:N", "optional (supporting source)"),
    ("routing_rule", "assignment", "1:N", "optional (initial assignments)"),
]


def dictionary_markdown() -> str:
    L = ["# Data dictionary", "",
         "_Generated from `src/campus_support/schema.py` — do not edit by hand (`make docs`)._", "",
         "Conventions: timestamps are naive campus-local ISO-8601 (`YYYY-MM-DDTHH:MM:SS`), minute granular; "
         "dates `YYYY-MM-DD`; booleans `true/false` in CSV, `true/false` in JSON, `1/0` in SQL; "
         "NULL = empty CSV cell / JSON null. IDs are immutable and zero-padded.", "",
         "## ID conventions", "",
         "| Entity | Pattern | Example |", "|---|---|---|",
         "| Ticket | `TKT-2026-NNNNNN` | TKT-2026-000001 |",
         "| Message | `MSG-<ticket-id>-NNN` | MSG-TKT-2026-000001-001 |",
         "| Knowledge article | `KB-NNNNNN` | KB-000001 |",
         "| Policy document | `POL-<domain>-2026-NNN` | POL-FIN-2026-001 |",
         "| SLA | `SLA-<ticket-id>` | SLA-TKT-2026-000001 |",
         "| Event / Assignment / Retrieval / Feedback | `EVT-/ASG-/RET-/FB-<ticket-id>[-NN]` | EVT-TKT-2026-000001-001 |", "",
         "## Ticket lifecycle (allowed transitions)", "",
         "| from_status | event_type | to_status |", "|---|---|---|"]
    for (f, e), t in TRANSITIONS.items():
        L.append(f"| {f or '(none)'} | {e} | {t} |")
    L += ["", "## Relationships and cardinality", "", "| Parent | Child | Cardinality | Optionality |", "|---|---|---|---|"]
    L += [f"| {p} | {c} | {card} | {opt} |" for p, c, card, opt in RELATIONSHIPS]
    for t in TABLES:
        L += ["", f"## `{t.name}`  ({t.kind})", "", t.desc, "", f"- **Primary key:** `{t.pk}`"]
        if t.unique_together:
            L.append("- **Composite unique:** " + "; ".join("(" + ", ".join(u) + ")" for u in t.unique_together))
        if t.cardinality:
            L.append(f"- **Cardinality:** {t.cardinality}")
        L += ["", "| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |",
              "|---|---|---|---|---|---|---|---|"]
        for c in t.cols:
            allowed = ", ".join(c.enum) if c.enum else (f"`{c.pattern}`" if c.pattern else "")
            if c.lo is not None or c.hi is not None:
                allowed = (allowed + " " if allowed else "") + f"[{'' if c.lo is None else c.lo}, {'' if c.hi is None else c.hi}]"
            L.append(f"| `{c.name}` | {c.typ} | {'Y' if c.req else 'N'} | {allowed.replace('|', '/')} | {c.unit} | "
                     f"{'Y' if (c.unique or c.name == t.pk) else ''} | {c.fk or ''} | {c.rule.replace('|', '/')} |")
    return "\n".join(L) + "\n"


def er_mermaid() -> str:
    L = ["erDiagram"]
    sym = {"1:N": "||--o{", "1:1": "||--||", "1:0..1": "||--o|"}
    for p, c, card, opt in RELATIONSHIPS:
        L.append(f"    {p} {sym[card]} {c} : \"{card}\"")
    return "\n".join(L) + "\n"
