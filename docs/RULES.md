# Documented business rules

All outcomes in the dataset follow these rules (implemented once in `src/campus_support/rules.py`). Time is naive
campus-local, minute granular.

## Ticket intake (inputs drawn by the generator)
Category (weighted), requester (role mix per domain; must be active on the creation date; heavy-tailed activity),
policy topic + asked fact, vagueness level (0 clear 80 % · 1 moderate 14 % · 2 vague 6 %), optional requester deadline (14 %),
channel. Creation time follows weekday / hour / term-start seasonality; holidays are quiet.

## R1 — Routing
Active routing rules matching `(category, requester role)` are filtered by effective dates; the **highest `precedence` wins**.
Generic rules (precedence 10) send each category to its domain's tier-1 team. Conditional rules (precedence 20):
instructor LMS/course-access problems and instructor grade-change petitions → same team, **priority raised to *high***.
A team may handle a category only if a row exists in `team_category_authorization` (tier 1: own domain; Academic
Administration: FIN/REG/ACC; Platform Administration: IT).

## P1 — Priority
`default_priority(category)`; then if a requester deadline exists: ≤ 24 h → **urgent**, ≤ 72 h → +1 level; then the routing
rule's `priority_override` (max). Boundaries are inclusive.

## K1 — Knowledge versions
A policy has versions 1..N. `effective_to` is inclusive and equals the next version's `effective_from − 1 day`; the
newest version is open-ended unless the policy is **retired** (then `effective_to = retired_date − 1`). Status is derived
relative to the dataset `as_of`: *current / superseded / retired*. The **current source** for a message is the version whose
window contains the message's send date (so a ticket created just before a version change is answered from the new version).

## Retrieval (recorded per ticket in `retrieval_result`)
`matched_article_id` = version in force at retrieval; none ⇒ `no_current_policy`. Confidence: clear questions ≥ 0.72;
moderate 0.46–0.69 before clarification and ≥ 0.72 after one round; vague 0.20–0.44 and still < 0.45 after two rounds.
`outcome = no_current_policy` if no article, else `low_confidence` if final confidence < 0.45, else `matched`.

## E1–E4 — Escalation (reason order = precedence)
| Code | Trigger | Tier-1 behaviour |
|---|---|---|
| E1 `human_review_required` | category flagged for human decision (aid-progress appeal, grade change, security incident, accommodation determination) | answer with citation, then escalate |
| E2 `no_current_policy` | no policy version in force (withdrawn policy) | no answer possible → escalation note |
| E3 `ambiguity_unresolved` | final confidence < 0.45 after two clarification requests and 16 business hours without a usable reply | escalate |
| E4 `urgent_deadline` | deadline ≤ 24 h **and** category is deadline-sensitive | answer, then escalate for expedite |

Escalation moves the ticket to the tier-1 team's `escalation_team_id`; tier 2 decides. Stalled moderate cases with no
reply are auto-closed (`closed_no_response`) after 6,720 business minutes (14 standard business days) — a documented *non*-escalation path.

## S1 — SLA
Targets are in **business minutes** of the routed team's calendar (`CAL-STD` Mon–Fri 09–17; `CAL-EXT` Mon–Fri 08–20 + Sat 10–14;
12 closure dates). `urgent 60/480 · high 240/1440 · normal 480/2400 · low 960/4800` (first response / resolution).
Due = `add_business_minutes(created_at, target)`. First response = first `support_staff` message. Resolution clock stops at
the first `resolved` event (else closure, else `as_of`). Breach ⇔ elapsed business minutes > target. Pauses while waiting
for the requester are **not** modelled (documented simplification).

## F1 — Feedback
~55 % of resolved tickets submit feedback. `rating = 5 − first-response breach − resolution breach − reopened − wrong-information
defect − (escalated, 50 %) ± noise(±1 on 25 %)`, clipped to 1–5, computed on the *true* business-hours clock.

## Lifecycle (append-only events)
`new → triaged → in_progress ⇄ pending_requester → escalated → in_progress → resolved → closed`, with
`resolved → reopened → in_progress`. The legal transition table is in `schema.TRANSITIONS` and in the data dictionary.
`ticket.status`, `current_team_id`, `resolved_at`, `closed_at`, `resolution_code`, `reopen_count`, `escalation_count`,
`message_count` are **derived** from those records.

## Injected anomalies (each on disjoint tickets; 2 % of tickets per type by default)
| `issue_type` | Mutation | Detector (input tables only) |
|---|---|---|
| `answer_cites_expired_policy` | first answer's citation + claim values switched to a superseded version whose fact differs | cited article not in force on `sent_at` |
| `ticket_routed_to_unauthorized_team` | initial assignment moved to a tier-1 team not authorised for the category | team not in authorisation bridge, or ≠ routing-rule target |
| `response_claims_unsupported_fact` | one claim value replaced by a value no version of the policy states | no cited article states that `fact_key = value` |
| `sla_clock_ignores_business_hours` | SLA due dates/elapsed computed on a 24×7 clock (`calendar_mode = calendar_24x7`) | due dates not reproducible on the declared business calendar |
| `escalation_not_triggered` | `escalated` event + tier-2 assignment removed; tier 1 closes a case that E1/E4 required to escalate | documented triggers present but no `escalated` event |

Counts of tickets and messages never change, and only labelled tickets are modified (tested).
