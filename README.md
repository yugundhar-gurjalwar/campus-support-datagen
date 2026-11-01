# Campus Support Routing — Synthetic Data Generator, Validator & Evaluator

A deterministic, **standard-library-only** Python pipeline that generates a relational dataset for the workflow
*"route student and faculty requests, retrieve policy-grounded answers, and track resolution and escalation"*
(financial aid, registration, IT, accessibility), injects **labelled** edge cases, validates everything, and scores
rule-based detectors against a **separate ground truth**.

| Spec requirement | Result (full build, seed `20261022`) |
|---|---|
| Volume | **5,000 tickets · 200 knowledge articles (48 policies) · 20,000 messages** (24 tables, ≈89k rows in total) |
| Entities | 11 core (Requester, Role, Term, PolicyDocument, KnowledgeArticle, Ticket, Message, Category, Assignment, SLA, ResolutionFeedback) + bridges / event tables — see [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) |
| Edge cases | 5 labelled anomaly types × 100 tickets (expired-policy citation, unauthorised team, unsupported claim, SLA ignoring business hours, escalation not triggered) |
| Validation | 20/20 checks pass ([`validation_summary.md`](data/full/metadata/validation_summary.md)) |
| Detection | precision = recall = 1.0 on all 5 anomaly types ([`evaluation_report.md`](data/full/metadata/evaluation_report.md)) |
| Reproducibility | two regenerations + committed manifest: all 53 file checksums identical ([`reproducibility_report.json`](data/full/metadata/reproducibility_report.json)) |
| Tests | 56 pytest tests |

## Quick start

Requires **Python ≥ 3.10**. No third-party runtime dependencies.

```bash
git clone https://github.com/yugundhar-gurjalwar/campus-support-datagen.git
cd campus-support-datagen
pip install -e ".[dev]"          # optional: installs pytest + the `campus-support` command

# full dataset (≈7 s): generate → export → validate → evaluate → write reports
python -m campus_support generate --out data/full

# the same generator at starter scale
python -m campus_support generate --tickets 250 --articles 40 --out data/starter

python -m pytest -q               # 56 tests, ≈6 s
```

Without installing, prefix commands with `PYTHONPATH=src`. `make all` runs everything (docs, both datasets, repro check, tests).

### Verify key behaviour

```bash
python -m campus_support validate     --data data/full      # structural + lifecycle + reconciliation checks (exit 1 on failure)
python -m campus_support evaluate     --data data/full      # detectors (input tables only) vs ground truth
python -m campus_support repro-check  --data data/full      # regenerate twice, compare row counts + SHA-256 to each other and to the manifest
```

Load the SQL seed and query it yourself (each query returns exactly the 100 injected cases, matching `ground_truth/`):

```bash
sqlite3 :memory: ".read data/full/sql/schema.sql" ".read data/full/sql/seed.sql" \
 "SELECT COUNT(DISTINCT m.ticket_id) FROM message_citation c JOIN message m USING(message_id)
    JOIN knowledge_article a USING(article_id)
   WHERE a.effective_to IS NOT NULL AND date(m.sent_at) > a.effective_to;"      -- answers citing an expired version → 100
```
```sql
SELECT COUNT(*) FROM sla WHERE calendar_mode = 'calendar_24x7';                  -- SLA clock ignores business hours → 100
SELECT COUNT(*) FROM assignment a JOIN ticket t USING(ticket_id)
  LEFT JOIN team_category_authorization z ON z.team_id=a.team_id AND z.category_id=t.category_id
 WHERE z.authorization_id IS NULL;                                               -- routed to unauthorised team → 100
SELECT COUNT(*) FROM message_claim cl WHERE NOT EXISTS (
  SELECT 1 FROM message_citation c JOIN article_fact f ON f.article_id=c.article_id
   WHERE c.message_id=cl.message_id AND f.fact_key=cl.fact_key AND f.fact_value=cl.claimed_value); -- unsupported claims → 100
```
> `data/full/json/` and `data/full/sql/seed.sql` (≈42 MB) are not committed; `python -m campus_support generate --out data/full`
> recreates them byte-for-byte (checksums are in `data/full/metadata/manifest.json`). `data/starter/` has every format committed.

## What gets generated

```
data/<scale>/
├── csv/             24 input tables (the only files a model/analyst should use as features)
├── json/            same tables, one JSON array per file
├── sql/             schema.sql (PK/FK/CHECK enforced) + seed.sql (parents before children)
├── ground_truth/    ground_truth_expected.csv   per-ticket expected team/priority/escalation/policy/article + case tags
│                    ground_truth_anomalies.csv one row per injected defect: entity, field, original → injected value
│                    ground_truth.json          both of the above
└── metadata/        manifest.json (rows + SHA-256) · run_config.json · source_manifest.json
                     validation_summary.{md,json} · evaluation_report.{md,json} · reproducibility_report.json
```

**Design in one paragraph.** Master data (roles, terms, calendars, teams, 16 categories, authorisation bridge, SLA tiers,
routing rules, 48 policies with 200 dated article *versions* and machine-checkable facts, 2,063 people) is generated first.
Tickets then draw only *intake* attributes (category, requester, topic, vagueness, deadline). Routing, priority, retrieval
outcome, escalation, SLA clocks, resolution and feedback are **derived by the documented rules** in
[`docs/RULES.md`](docs/RULES.md) — never drawn independently. State changes are append-only `ticket_event` /
`assignment` / `message` rows; ticket `status`, SLA elapsed/breach and feedback scores are computed from them. Only after
a valid baseline exists are the five defects injected on disjoint tickets and written to ground truth.

## Repository layout

| Path | Purpose |
|---|---|
| `src/campus_support/schema.py` | single source of truth: 24 tables, types, enums, FKs, lifecycle → DDL, data dictionary, ER diagram |
| `catalog.py`, `master.py` | static content and master-table generation |
| `rules.py` | documented routing / priority / versioning / escalation / SLA rules (shared by generator **and** evaluator) |
| `simulate.py`, `finalize.py` | ticket lifecycles; exact message-volume fitting; derived values |
| `anomalies.py` | the five labelled edge-case injectors |
| `validate.py`, `evaluate.py` | Step 8 structural validation; detectors + acceptance metrics |
| `io_export.py`, `cli.py`, `pipeline.py` | exporters/loaders, CLI, orchestration |
| `tests/` | 56 tests (unit, invariants, validator negative tests, exports, CLI, reproducibility) |
| `docs/` | `DESIGN.md` (assumptions, trade-offs, limits), `RULES.md`, `DATA_DICTIONARY.md`, `ER_DIAGRAM.md`, `AI_USAGE.md`, `PROMPT_HISTORY.md` |

## Parameters

`--seed` (default 20261022) · `--tickets` (5000) · `--articles` (200) · `--messages-per-ticket` (4.0 ⇒ 20,000) ·
`--anomaly-rate` (0.02 per type). Everything is a pure function of these; there are no clocks, no global RNG state and no
network access. Each ticket's lifecycle draws come from its own named RNG stream, isolating tickets from one another.

## Provenance & lawful use

No external data is used ([`source_manifest.json`](data/full/metadata/source_manifest.json)). All policies, people and messages
are synthetic; e-mails use the reserved `campus.example.edu` domain.

## Honest scope notes

See [`docs/DESIGN.md`](docs/DESIGN.md#limitations) — most importantly: the detectors share rule code with the generator
(so perfect recall demonstrates rule-consistency, not generalisation), and message text is template-based.
AI usage is disclosed in [`docs/AI_USAGE.md`](docs/AI_USAGE.md).
