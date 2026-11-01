# Data dictionary

_Generated from `src/campus_support/schema.py` — do not edit by hand (`make docs`)._

Conventions: timestamps are naive campus-local ISO-8601 (`YYYY-MM-DDTHH:MM:SS`), minute granular; dates `YYYY-MM-DD`; booleans `true/false` in CSV, `true/false` in JSON, `1/0` in SQL; NULL = empty CSV cell / JSON null. IDs are immutable and zero-padded.

## ID conventions

| Entity | Pattern | Example |
|---|---|---|
| Ticket | `TKT-2026-NNNNNN` | TKT-2026-000001 |
| Message | `MSG-<ticket-id>-NNN` | MSG-TKT-2026-000001-001 |
| Knowledge article | `KB-NNNNNN` | KB-000001 |
| Policy document | `POL-<domain>-2026-NNN` | POL-FIN-2026-001 |
| SLA | `SLA-<ticket-id>` | SLA-TKT-2026-000001 |
| Event / Assignment / Retrieval / Feedback | `EVT-/ASG-/RET-/FB-<ticket-id>[-NN]` | EVT-TKT-2026-000001-001 |

## Ticket lifecycle (allowed transitions)

| from_status | event_type | to_status |
|---|---|---|
| (none) | created | new |
| new | routed | triaged |
| triaged | assigned | in_progress |
| in_progress | clarification_requested | pending_requester |
| pending_requester | clarification_received | in_progress |
| in_progress | escalated | escalated |
| pending_requester | escalated | escalated |
| escalated | assigned | in_progress |
| in_progress | reassigned | in_progress |
| in_progress | resolved | resolved |
| pending_requester | closed | closed |
| resolved | closed | closed |
| resolved | reopened | reopened |
| reopened | assigned | in_progress |

## Relationships and cardinality

| Parent | Child | Cardinality | Optionality |
|---|---|---|---|
| role | requester | 1:N | required |
| team | requester | 1:N | optional (staff only) |
| business_calendar | calendar_hours | 1:N | required |
| business_calendar | team | 1:N | required |
| team | team | 1:0..1 | optional (tier-1 -> tier-2 escalation team) |
| team | team_category_authorization | 1:N | required |
| category | team_category_authorization | 1:N | required |
| category | routing_rule | 1:N | required |
| role | routing_rule | 1:N | optional (conditional rule) |
| team | routing_rule | 1:N | required |
| category | policy_document | 1:N | required |
| team | policy_document | 1:N | required |
| policy_document | knowledge_article | 1:N | required (versions) |
| knowledge_article | article_fact | 1:N | required |
| knowledge_article | article_category | 1:N | required |
| category | article_category | 1:N | required |
| requester | ticket | 1:N | required |
| term | ticket | 1:N | required |
| category | ticket | 1:N | required |
| ticket | ticket_event | 1:N | required |
| ticket | message | 1:N | required |
| ticket | assignment | 1:N | required |
| ticket | sla | 1:1 | required |
| sla_policy | sla | 1:N | required |
| ticket | retrieval_result | 1:1 | required |
| ticket | resolution_feedback | 1:0..1 | optional |
| message | message_citation | 1:N | optional |
| knowledge_article | message_citation | 1:N | optional |
| message | message_claim | 1:N | optional |
| knowledge_article | message_claim | 1:N | optional (supporting source) |
| routing_rule | assignment | 1:N | optional (initial assignments) |

## `role`  (master)

Actor roles recognised by the platform.

- **Primary key:** `role_id`
- **Cardinality:** Role 1:N Requester

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `role_id` | str | Y | `^ROLE-[A-Z]+$` |  | Y |  | immutable |
| `role_name` | str | Y | Learner, Instructor, Academic Administrator, Support Staff, Platform Administrator |  | Y |  |  |
| `role_group` | str | Y | requester, staff, admin |  |  |  |  |
| `can_file_tickets` | bool | Y |  |  |  |  |  |
| `can_resolve_tickets` | bool | Y |  |  |  |  |  |
| `description` | text | Y |  |  |  |  |  |

## `term`  (master)

Academic terms; ticket.term_id is the term in session (or next term during breaks) at creation.

- **Primary key:** `term_id`
- **Cardinality:** Term 1:N Ticket

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `term_id` | str | Y | `^TERM-\d{4}-(SP/SU/FA)$` |  | Y |  |  |
| `term_name` | str | Y |  |  |  |  |  |
| `start_date` | date | Y |  |  |  |  |  |
| `end_date` | date | Y |  |  |  |  | end_date > start_date |
| `registration_open_date` | date | Y |  |  |  |  | <= start_date |
| `status` | str | Y | completed, active, upcoming |  |  |  | derived from dataset as_of date |

## `business_calendar`  (master)

Named business-hours calendars used by SLA clocks.

- **Primary key:** `calendar_id`
- **Cardinality:** Calendar 1:N CalendarHours; Calendar 1:N Team; Calendar 1:N SLA

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `calendar_id` | str | Y | `^CAL-[A-Z0-9]+$` |  | Y |  |  |
| `name` | str | Y |  |  |  |  |  |
| `timezone_label` | str | Y | campus-local |  |  |  | all timestamps are naive campus-local time |

## `calendar_hours`  (master)

Open window per weekday for a calendar (absent weekday = closed).

- **Primary key:** `hours_id`
- **Composite unique:** (calendar_id, weekday)

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `hours_id` | str | Y | `^CH-CAL-[A-Z0-9]+-\d$` |  | Y |  |  |
| `calendar_id` | str | Y |  |  |  | business_calendar.calendar_id |  |
| `weekday` | int | Y | [0, 6] |  |  |  | Mon=0 |
| `open_minute` | int | Y | [0, 1440] | minutes after midnight |  |  |  |
| `close_minute` | int | Y | [0, 1440] | minutes after midnight |  |  | > open_minute |

## `holiday`  (master)

Campus closures; no business minutes accrue on these dates.

- **Primary key:** `holiday_id`

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `holiday_id` | str | Y | `^HOL-\d{8}$` |  | Y |  |  |
| `holiday_date` | date | Y |  |  | Y |  |  |
| `name` | str | Y |  |  |  |  |  |

## `team`  (master)

Support teams. Tier 1 = domain desks; tier 2 = escalation teams.

- **Primary key:** `team_id`
- **Cardinality:** Team 1:N Requester(staff); Team 1:N Assignment; Team 1:0..1 EscalationTeam

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `team_id` | str | Y | `^TEAM-[A-Z]+$` |  | Y |  |  |
| `team_name` | str | Y |  |  |  |  |  |
| `tier` | int | Y | [1, 2] |  |  |  |  |
| `domain` | str | Y | FIN, REG, IT, ACC, ADMIN, PLAT |  |  |  |  |
| `calendar_id` | str | Y |  |  |  | business_calendar.calendar_id |  |
| `escalation_team_id` | str | N |  |  |  | team.team_id | tier-1 teams only; must be tier 2 |
| `active` | bool | Y |  |  |  |  |  |

## `requester`  (master)

Every person in the system (ticket requesters and staff/admin handlers). Synthetic identities only.

- **Primary key:** `requester_id`
- **Cardinality:** Requester 1:N Ticket; Requester(staff) 1:N Assignment

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `requester_id` | str | Y | `^REQ-\d{6}$` |  | Y |  |  |
| `role_id` | str | Y |  |  |  | role.role_id |  |
| `full_name` | str | Y |  |  |  |  |  |
| `email` | str | Y | `^[a-z0-9._-]+@campus\.example\.edu$` |  | Y |  | reserved example domain; no real PII |
| `department_code` | str | Y | CS, BUS, NUR, ENG, ART, BIO, FAO, REGO, ITS, DSS, ADM |  |  |  |  |
| `program_level` | str | N | undergraduate, graduate, non_degree |  |  |  | learners only |
| `team_id` | str | N |  |  |  | team.team_id | set iff role is Support Staff / Academic Admin / Platform Admin handler |
| `status` | str | Y | active, inactive |  |  |  |  |
| `active_from` | date | Y |  |  |  |  |  |
| `active_to` | date | N |  |  |  |  | >= active_from; null = still active |

## `category`  (master)

Request categories (4 domains x 4 sub-topics).

- **Primary key:** `category_id`
- **Cardinality:** Category 1:N Ticket; Category N:M Team; Category N:M Article

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `category_id` | str | Y | `^CAT-(FIN/REG/IT/ACC)-\d{2}$` |  | Y |  |  |
| `domain` | str | Y | FIN, REG, IT, ACC |  |  |  |  |
| `domain_name` | str | Y | financial_aid, registration, it, accessibility |  |  |  |  |
| `category_name` | str | Y |  |  |  |  |  |
| `default_priority` | str | Y | low, normal, high, urgent |  |  |  |  |
| `human_review_required` | bool | Y |  |  |  |  | escalation rule E1: always needs a tier-2 decision |
| `deadline_sensitive` | bool | Y |  |  |  |  | escalation rule E4 applies when a deadline is <= 24h away |
| `description` | text | Y |  |  |  |  |  |

## `team_category_authorization`  (bridge)

Which team may legitimately handle which category (N:M bridge).

- **Primary key:** `authorization_id`
- **Composite unique:** (team_id, category_id)
- **Cardinality:** Team N:M Category

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `authorization_id` | str | Y | `^AUTH-\d{6}$` |  | Y |  |  |
| `team_id` | str | Y |  |  |  | team.team_id |  |
| `category_id` | str | Y |  |  |  | category.category_id |  |
| `effective_from` | date | Y |  |  |  |  |  |
| `effective_to` | date | N |  |  |  |  |  |

## `sla_policy`  (master)

SLA targets per priority, measured in business minutes of the handling team's calendar.

- **Primary key:** `sla_policy_id`
- **Cardinality:** SlaPolicy 1:N SLA

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `sla_policy_id` | str | Y | `^SLAP-[A-Z]+$` |  | Y |  |  |
| `priority` | str | Y | low, normal, high, urgent |  | Y |  |  |
| `first_response_minutes` | int | Y | [1, ] | business minutes |  |  |  |
| `resolution_minutes` | int | Y | [1, ] | business minutes |  |  | > first_response_minutes |
| `effective_from` | date | Y |  |  |  |  |  |
| `effective_to` | date | N |  |  |  |  |  |

## `routing_rule`  (master)

Routing rules; highest precedence matching rule wins.

- **Primary key:** `routing_rule_id`
- **Cardinality:** Category 1:N RoutingRule; RoutingRule 0..N:1 Assignment

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `routing_rule_id` | str | Y | `^RR-\d{3}$` |  | Y |  |  |
| `category_id` | str | Y |  |  |  | category.category_id |  |
| `requester_role_id` | str | N |  |  |  | role.role_id | null = any role (generic rule) |
| `target_team_id` | str | Y |  |  |  | team.team_id | team must be authorised for category_id |
| `priority_override` | str | N | low, normal, high, urgent |  |  |  |  |
| `precedence` | int | Y | [1, ] |  |  |  |  |
| `effective_from` | date | Y |  |  |  |  |  |
| `effective_to` | date | N |  |  |  |  |  |
| `description` | text | Y |  |  |  |  |  |

## `policy_document`  (master)

Policy documents (synthetic). Each has 1..N dated versions held as knowledge articles.

- **Primary key:** `policy_id`
- **Cardinality:** PolicyDocument 1:N KnowledgeArticle (versions)

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `policy_id` | str | Y | `^POL-(FIN/REG/IT/ACC)-2026-\d{3}$` |  | Y |  |  |
| `domain` | str | Y | FIN, REG, IT, ACC |  |  |  |  |
| `title` | str | Y |  |  |  |  |  |
| `category_id` | str | Y |  |  |  | category.category_id |  |
| `owner_team_id` | str | Y |  |  |  | team.team_id |  |
| `status` | str | Y | active, retired |  |  |  | derived: retired iff newest version expired before as_of |
| `first_effective_date` | date | Y |  |  |  |  |  |
| `retired_date` | date | N |  |  |  |  |  |
| `is_synthetic` | bool | Y |  |  |  |  | always true: no external data used |
| `source_note` | text | Y |  |  |  |  |  |

## `knowledge_article`  (master)

One published VERSION of a policy document, with effective dates.

- **Primary key:** `article_id`
- **Composite unique:** (policy_id, version_no)
- **Cardinality:** Article 1:N ArticleFact; Article N:M Category; Article N:M Message

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `article_id` | str | Y | `^KB-\d{6}$` |  | Y |  |  |
| `policy_id` | str | Y |  |  |  | policy_document.policy_id |  |
| `version_no` | int | Y | [1, ] |  |  |  | contiguous 1..N per policy |
| `title` | str | Y |  |  |  |  |  |
| `body` | text | Y |  |  |  |  |  |
| `effective_from` | date | Y |  |  |  |  |  |
| `effective_to` | date | N |  |  |  |  | inclusive; = next version effective_from - 1 day; null = open-ended |
| `status` | str | Y | current, superseded, retired |  |  |  | derived relative to as_of |
| `supersedes_article_id` | str | N |  |  |  | knowledge_article.article_id | previous version of same policy |
| `author_id` | str | Y |  |  |  | requester.requester_id |  |
| `published_at` | datetime | Y |  |  |  |  | <= effective_from + 0d |

## `article_fact`  (master)

Machine-checkable facts stated by an article version (used to verify claims).

- **Primary key:** `fact_id`
- **Composite unique:** (article_id, fact_key)

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `fact_id` | str | Y | `^FACT-\d{6}$` |  | Y |  |  |
| `article_id` | str | Y |  |  |  | knowledge_article.article_id |  |
| `fact_key` | str | Y |  |  |  |  |  |
| `fact_value` | str | Y |  |  |  |  |  |
| `unit` | str | N |  |  |  |  |  |

## `article_category`  (bridge)

Article <-> category applicability (N:M bridge).

- **Primary key:** `article_category_id`
- **Composite unique:** (article_id, category_id)
- **Cardinality:** Article N:M Category

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `article_category_id` | str | Y | `^AC-\d{6}$` |  | Y |  |  |
| `article_id` | str | Y |  |  |  | knowledge_article.article_id |  |
| `category_id` | str | Y |  |  |  | category.category_id |  |
| `is_primary` | bool | Y |  |  |  |  |  |

## `ticket`  (transaction)

A support request. Intake fields are inputs; status/current_team_id/resolved_at/closed_at/resolution_code/*_count are DERIVED from event, assignment and message records.

- **Primary key:** `ticket_id`
- **Cardinality:** Ticket 1:N Event/Message/Assignment; Ticket 1:1 SLA; Ticket 1:1 RetrievalResult; Ticket 1:0..1 Feedback

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `ticket_id` | str | Y | `^TKT-2026-\d{6}$` |  | Y |  |  |
| `requester_id` | str | Y |  |  |  | requester.requester_id | requester role must be able to file tickets and be active at created_at |
| `term_id` | str | Y |  |  |  | term.term_id |  |
| `category_id` | str | Y |  |  |  | category.category_id |  |
| `priority` | str | Y | low, normal, high, urgent |  |  |  | output of priority rule P1 at creation |
| `channel` | str | Y | portal, email, chat, phone |  |  |  |  |
| `subject` | str | Y |  |  |  |  |  |
| `created_at` | datetime | Y |  | campus-local minute |  |  |  |
| `requester_deadline_at` | datetime | N |  |  |  |  | requester-stated deadline; > created_at |
| `status` | str | Y | new, triaged, in_progress, pending_requester, escalated, resolved, reopened, closed |  |  |  | = to_status of last ticket_event |
| `current_team_id` | str | N |  |  |  | team.team_id | team of the open assignment; null when none open |
| `resolved_at` | datetime | N |  |  |  |  | time of last 'resolved' event |
| `closed_at` | datetime | N |  |  |  |  |  |
| `resolution_code` | str | N | answered_by_policy, resolved_after_escalation, closed_no_response |  |  |  |  |
| `reopen_count` | int | Y | [0, ] |  |  |  | = count of 'reopened' events |
| `escalation_count` | int | Y | [0, ] |  |  |  | = count of 'escalated' events |
| `message_count` | int | Y | [1, ] |  |  |  | = count of message rows |

## `ticket_event`  (event)

Append-only lifecycle history; one row per state change. Never updated.

- **Primary key:** `event_id`
- **Composite unique:** (ticket_id, event_seq)

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `event_id` | str | Y | `^EVT-TKT-2026-\d{6}-\d{3}$` |  | Y |  |  |
| `ticket_id` | str | Y |  |  |  | ticket.ticket_id |  |
| `event_seq` | int | Y | [1, ] |  |  |  | contiguous per ticket |
| `event_type` | str | Y | created, routed, assigned, clarification_requested, clarification_received, escalated, reassigned, resolved, reopened, closed |  |  |  |  |
| `from_status` | str | N | new, triaged, in_progress, pending_requester, escalated, resolved, reopened, closed |  |  |  |  |
| `to_status` | str | Y | new, triaged, in_progress, pending_requester, escalated, resolved, reopened, closed |  |  |  | must equal TRANSITIONS[(from_status, event_type)] |
| `event_at` | datetime | Y |  |  |  |  | non-decreasing in event_seq |
| `actor_type` | str | Y | requester, support_staff, system |  |  |  |  |
| `actor_id` | str | N |  |  |  | requester.requester_id |  |
| `team_id` | str | N |  |  |  | team.team_id |  |
| `reason_code` | str | N | human_review_required, no_current_policy, ambiguity_unresolved, urgent_deadline, routing_rule, initial_pickup, tier2_pickup, reopen_pickup, staff_reassign, policy_answer, tier2_decision, requester_reopened, no_response, auto_close_after_resolution, needs_clarification, clarification_provided |  |  |  |  |

## `retrieval_result`  (transaction)

Outcome of the policy-retrieval step run when the ticket is routed.

- **Primary key:** `retrieval_id`
- **Cardinality:** Ticket 1:1 RetrievalResult

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `retrieval_id` | str | Y | `^RET-TKT-2026-\d{6}$` |  | Y |  |  |
| `ticket_id` | str | Y |  |  | Y | ticket.ticket_id |  |
| `retrieved_at` | datetime | Y |  |  |  |  |  |
| `matched_policy_id` | str | N |  |  |  | policy_document.policy_id |  |
| `matched_article_id` | str | N |  |  |  | knowledge_article.article_id | version effective at retrieved_at; null if none |
| `initial_confidence` | float | Y | [0, 1] |  |  |  |  |
| `final_confidence` | float | Y | [0, 1] |  |  |  | after clarification rounds |
| `outcome` | str | Y | matched, low_confidence, no_current_policy |  |  |  | no_current_policy if no article effective; else low_confidence if final_confidence < 0.45; else matched |

## `message`  (event)

Conversation history. Append-only.

- **Primary key:** `message_id`
- **Composite unique:** (ticket_id, message_seq)

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `message_id` | str | Y | `^MSG-TKT-2026-\d{6}-\d{3}$` |  | Y |  |  |
| `ticket_id` | str | Y |  |  |  | ticket.ticket_id |  |
| `message_seq` | int | Y | [1, ] |  |  |  | contiguous per ticket; id suffix = seq |
| `sender_type` | str | Y | requester, support_staff, system |  |  |  |  |
| `sender_id` | str | N |  |  |  | requester.requester_id | null iff system |
| `message_type` | str | Y | question, system_ack, clarification_request, clarification_reply, answer, agent_update, escalation_note, handoff_response, requester_followup, reopen_request, thanks |  |  |  |  |
| `sent_at` | datetime | Y |  |  |  |  | >= ticket.created_at; non-decreasing in seq |
| `body` | text | Y |  |  |  |  |  |

## `message_citation`  (bridge)

Message <-> article version cited (N:M bridge). Records the version cited.

- **Primary key:** `citation_id`
- **Composite unique:** (message_id, article_id)
- **Cardinality:** Message N:M Article

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `citation_id` | str | Y | `^CIT-\d{6}$` |  | Y |  |  |
| `message_id` | str | Y |  |  |  | message.message_id |  |
| `article_id` | str | Y |  |  |  | knowledge_article.article_id |  |
| `article_version_no` | int | Y | [1, ] |  |  |  | must equal knowledge_article.version_no |
| `citation_rank` | int | Y | [1, ] |  |  |  |  |

## `message_claim`  (event)

Verifiable factual statements made in a message.

- **Primary key:** `claim_id`
- **Cardinality:** Message 1:N Claim

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `claim_id` | str | Y | `^CLM-\d{6}$` |  | Y |  |  |
| `message_id` | str | Y |  |  |  | message.message_id |  |
| `fact_key` | str | Y |  |  |  |  |  |
| `claimed_value` | str | Y |  |  |  |  |  |
| `supporting_article_id` | str | N |  |  |  | knowledge_article.article_id | null = no supporting source |

## `assignment`  (event)

Who handled the ticket and when; closed, never overwritten.

- **Primary key:** `assignment_id`
- **Composite unique:** (ticket_id, assignment_seq)

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `assignment_id` | str | Y | `^ASG-TKT-2026-\d{6}-\d{2}$` |  | Y |  |  |
| `ticket_id` | str | Y |  |  |  | ticket.ticket_id |  |
| `assignment_seq` | int | Y | [1, ] |  |  |  |  |
| `team_id` | str | Y |  |  |  | team.team_id |  |
| `assignee_id` | str | Y |  |  |  | requester.requester_id | assignee.team_id must equal team_id |
| `assignment_type` | str | Y | initial, reassignment, escalation, reopen |  |  |  |  |
| `routing_rule_id` | str | N |  |  |  | routing_rule.routing_rule_id | set on 'initial' only |
| `assigned_at` | datetime | Y |  |  |  |  |  |
| `ended_at` | datetime | N |  |  |  |  | >= assigned_at |
| `end_reason` | str | N | escalated, reassigned, resolved |  |  |  |  |

## `sla`  (derived)

SLA clock per ticket. Due dates/elapsed/breach flags are computed from calendar + events + messages.

- **Primary key:** `sla_id`
- **Cardinality:** Ticket 1:1 SLA

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `sla_id` | str | Y | `^SLA-TKT-2026-\d{6}$` |  | Y |  |  |
| `ticket_id` | str | Y |  |  | Y | ticket.ticket_id |  |
| `sla_policy_id` | str | Y |  |  |  | sla_policy.sla_policy_id |  |
| `calendar_id` | str | Y |  |  |  | business_calendar.calendar_id |  |
| `calendar_mode` | str | Y | business_hours, calendar_24x7 |  |  |  | must be business_hours |
| `clock_start_at` | datetime | Y |  |  |  |  | = ticket.created_at |
| `first_response_due_at` | datetime | Y |  |  |  |  |  |
| `resolution_due_at` | datetime | Y |  |  |  |  |  |
| `first_response_at` | datetime | N |  |  |  |  | first support_staff message |
| `first_resolved_at` | datetime | N |  |  |  |  | first 'resolved' event |
| `resolution_clock_stop_at` | datetime | Y |  |  |  |  | first_resolved_at, else closed_at, else dataset as_of |
| `first_response_elapsed_minutes` | int | N |  | minutes (per calendar_mode) |  |  |  |
| `resolution_elapsed_minutes` | int | Y |  | minutes (per calendar_mode) |  |  |  |
| `first_response_breached` | bool | Y |  |  |  |  |  |
| `resolution_breached` | bool | Y |  |  |  |  |  |

## `resolution_feedback`  (event)

Requester feedback after resolution (optional; ~half of resolved tickets).

- **Primary key:** `feedback_id`
- **Cardinality:** Ticket 1:0..1 Feedback

| Field | Type | Req | Allowed values / pattern | Unit | Unique | FK | Validation rule |
|---|---|---|---|---|---|---|---|
| `feedback_id` | str | Y | `^FB-TKT-2026-\d{6}$` |  | Y |  |  |
| `ticket_id` | str | Y |  |  | Y | ticket.ticket_id |  |
| `submitted_at` | datetime | Y |  |  |  |  | > last resolved event |
| `rating` | int | Y | [1, 5] |  |  |  | rule score from SLA breaches/reopen, +/-1 noise on ~25% |
| `issue_resolved` | bool | Y |  |  |  |  | false iff ticket was reopened |
| `comment_code` | str | Y | fast_and_clear, helpful, slow, unclear, wrong_or_outdated, unresolved, none |  |  |  |  |
