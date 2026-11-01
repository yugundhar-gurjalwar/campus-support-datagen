# Design notes: problem, assumptions, decisions, testing, limitations

## 1. Problem as I understood it
Generate a **medium-complexity relational dataset** for a campus support workflow — route requests, answer from
versioned policy articles, track resolution/escalation — such that (a) every outcome follows documented rules, (b) five
specific defects are injected **and labelled** without corrupting anything else, (c) derived values reconcile, (d) ground
truth is kept apart from inputs, and (e) the whole thing is reproducible from a seed at two scales. The deliverable is the
*generator + validator + evidence*, not a single static CSV.

## 2. Assumptions (where the brief was open)
| Topic | Assumption |
|---|---|
| "Requester" | one `requester` table for every person (learners, instructors, administrators **and** handlers); `role` + `team_id` distinguish them |
| Messages | 20,000 = 4.0 per ticket exactly; parameterised as `--messages-per-ticket` |
| Articles | each article row is one **version** of a policy document (48 policies, 200 versions) — this is how "versions and effective dates" and "article version is recorded" are modelled |
| "Current source" | the version in force on the **message's send date** (not on ticket creation) |
| Time | naive campus-local timestamps, minute granularity; no DST/time zones |
| Snapshot | `as_of = 2026-10-31 23:59`; tickets created 2026-01-05 … 2026-10-23, so a small backlog is genuinely open |
| Escalation | = hand-off to the tier-2 team named on the tier-1 team; "human" review is a documented trigger, not a role |
| External data | none (the brief makes it optional); policy text is authored by the generator |

## 3. Key decisions and trade-offs
1. **Rules first, one implementation.** `rules.py` holds routing/priority/versioning/escalation/SLA logic and is used by
   the generator *and* the evaluator. *Benefit:* a rule change cannot silently diverge. *Cost:* see Limitation 1.
2. **Derive, don't draw** (Step 5/6). Ticket `status`, `current_team_id`, SLA elapsed/breach, feedback ratings, counts are
   computed from event/assignment/message rows after the fact; the validator re-derives them independently of the generator
   code path (SLA recomputed from the calendar tables read back from CSV).
3. **Baseline first, then mutate.** Anomalies are applied to a valid baseline on disjoint tickets with an
   `original → injected` record, which guarantees unambiguous labels and lets a test prove *only labelled tickets changed*.
4. **Make claims machine-checkable.** `article_fact` + `message_claim` + `message_citation` turn "response claims an unsupported
   fact" into an exact join rather than an NLP judgement; versions change at least one fact so stale citations are materially wrong.
5. **A `retrieval_result` table.** Escalation expectations (confidence, no-current-policy) must be derivable from *inputs*, else the
   "escalation not triggered" detector would need ground truth. This also models the "retrieve policy-grounded answers" step.
6. **Exact message volume.** The lifecycle skeleton yields ≈3.05 messages/ticket; optional, type-appropriate follow-ups
   (acknowledgements, nudges, thanks) are inserted into gaps until the count is exactly 4.0×tickets. Hence the
   `--messages-per-ticket ≥ 3.5` floor (fails loudly rather than silently padding). The anomaly step never changes counts.
7. **stdlib only.** Zero setup, and reproducibility doesn't depend on numpy/pandas versions. Cost: more hand-written code.
8. **Schema as data** (`schema.py`) drives DDL, data dictionary, ER diagram, validators and loaders — docs cannot drift from code.
9. **Validate the exported files**, not in-memory objects: `generate` re-loads the CSVs, loads the SQL into SQLite with
   `PRAGMA foreign_keys=ON`, and checks the ground truth never appears in input tables.

## 4. How I know it works (evidence, not assertion)
- **Validation** (`data/full/metadata/validation_summary.md`): PK uniqueness, FK integrity, enums/patterns/ranges, ID
  conventions, date ordering, version-chain contiguity, lifecycle transitions, derived-value reconciliation, duplicates, SQL load.
- **Negative tests** (12 in `tests/test_validation_export.py`): each corrupts a copy of the data (broken FK, duplicate PK, illegal
  transition, drifted SLA, reordered dates, version gap, wrong assignee, …) and asserts the validator **fails the right check**.
- **Detector scoring**: precision/recall 1.0 for all five anomaly types; **0** unexplained escalations; clean tickets match
  expected team/priority/escalation 100 %. Four of the five can also be reproduced with plain SQL (README).
- **Reproducibility**: two regenerations + the committed manifest agree on 53 SHA-256 checksums, and checksums are
  identical under different `PYTHONHASHSEED` values; a different seed *does* fail the check (tested).
- **Realism checks**: skewed priorities (normal 68 % / high 15 % / low 11 % / urgent 5 %), weekday/term seasonality,
  escalation 17.9 %, first-response breach 5–8 %, resolution breach 11–34 % by priority (higher for urgent/high because
  escalated work dominates those tiers), mean rating lower on defective tickets (4.19 vs 4.59).

### Defects found in my own work during development (and fixed at the source)
1. Validator flagged 5 requesters whose `active_to` preceded `active_from` — independent date draws in `master.py`.
2. Inspecting message-type counts showed **zero** `system_ack` messages: a window filter in the follow-up placer was too strict.
3. A test that corrupted a primary key crashed the validator with `KeyError`; it now reports the failure and aborts deeper checks gracefully.
4. All tickets were closed at the snapshot (no backlog), so the creation window was extended to 2026-10-23.

## 5. Limitations
1. **Detectors share rule code with the generator.** Perfect recall proves internal consistency and correct labelling, *not*
   that the detectors generalise. An independent checker (different implementation, or an LLM judge) should be benchmarked on this data.
2. **Template text.** Message bodies come from small template pools with fact substitution; lexical diversity is low, so this
   is not suitable for training or evaluating NLP models on language realism.
3. **Retrieval signal is synthetic.** `initial/final_confidence` is drawn from bands tied to vagueness; combined with the
   category flags it predicts escalation perfectly *by construction*. Treat it as a documented rule feature, not a learned score.
4. **Simplified SLA.** No pause while pending the requester, no per-agent capacity/queueing, no time zones or DST, 12 closure dates.
5. **One anomaly per ticket.** Real defects co-occur; disjointness was chosen for unambiguous labels.
6. **Small open backlog** (11 open tickets) and a fairly high mean rating (4.55); both are tunable but untuned to any real institution.
7. **Python/stdlib RNG dependence.** Checksums were produced on CPython 3.13; other minor versions may change `random`
   algorithms. The repro check (`make repro`) will tell you immediately.
8. **No real PII, but names are drawn from small pools** so coincidental matches with real people are possible; e-mails use `example.edu`.

## 6. If I had more time
Independent detector implementations + an LLM-as-judge comparison; co-occurring anomalies; SLA pause/resume; agent
capacity model; richer text via a controlled paraphrase layer; property-based tests (Hypothesis) over random scales/seeds.
