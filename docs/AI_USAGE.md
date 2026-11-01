# AI usage disclosure

The YottaFlex guidelines allow LLM tools and ask for transparent disclosure: where AI accelerated the work, where it was
relied on heavily, and what was personally reviewed, changed or validated. This file is written to be accurate about
what the AI did; **Section 4 can only be completed by the candidate** and is deliberately left for him to fill in.

## 1. Tool
Claude (Anthropic; model *Claude Sonnet 5.5*) in an agentic coding session with file, shell and test-running tools.
The full human↔AI conversation is summarised in [`PROMPT_HISTORY.md`](PROMPT_HISTORY.md).

## 2. Where AI accelerated the work
- Reading the problem statement and turning its 10 generation steps into an architecture (schema → master → simulate →
  inject → derive → validate → export → reproduce).
- Writing essentially **all** of the source code, the 56 tests, the data dictionary generator, and the docs in this repository.
- Iterating on defects: running the pipeline, inspecting distributions, and fixing issues the validator/tests surfaced
  (see `DESIGN.md` §4 for the four concrete defects found and fixed during development).

## 3. Where I (the AI) was relied on heavily — and the risks that creates
| Area | Reliance | Risk a reviewer should probe |
|---|---|---|
| Domain model, rule design (routing, priority, E1–E4 escalation, SLA, versioning) | design proposed entirely by the AI | rules are plausible, not sourced from a real institution |
| Generator + anomaly injectors | AI-authored | injectors and detectors share `rules.py`, so perfect recall shows consistency, not independent detection (see `DESIGN.md` §5.1) |
| Tests | AI-authored, **including the tests that judge the AI's own code** | tests were written by the same author as the code; the negative tests were designed to reduce this, but independent review is valuable |
| Numbers in README/DESIGN | copied from generated reports by the AI | re-run `make all` and compare |

## 4. What I personally reviewed, changed and validated
> **Ran the project myself in a different environment from where it was built** (Windows, Python 3.14; built on
  Linux, Python 3.13): `pytest` gave 56 passed, `generate --out data/full` gave validation 20/20 and detector
  recall 1.0 on all five anomaly types, and `repro-check` confirmed two regenerations are identical.
 **Cross-platform reproducibility:**  regenerating on my machine left the committed data files unchanged, so output is byte-   identical across OS and Python versions.
 **Independent SQL cross-check:** I loaded the generated SQL into SQLite and ran the four README queries. They
  returned [100 each on the full dataset / 5 each on the starter dataset], matching the injected counts in
  `ground_truth_anomalies.csv`. The fifth type (escalation not triggered) has no SQL query and relies on the Python
  detector.
 **Traced one escalated ticket end-to-end** (`TKT-2026-000005`) across `ticket`, `ticket_event`, `assignment`,
  `message` and `sla`. Confirmed: two clarification requests → escalation for `ambiguity_unresolved` exactly 16
  business hours after the second request, hand-off to the tier-2 team, resolution and auto-close;
  `escalation_count` = 1 and `message_count` = 7 match the underlying rows. This ticket also carries the injected
  "SLA ignores business hours" defect (`calendar_mode = calendar_24x7`, due time 8 clock hours after creation),
  confirmed in `ground_truth_anomalies.csv` (GT-000001).
- **Where I disagree / would change things:** the detectors share rules.py with the generator, so perfect recall
  shows rule-consistency rather than independent detection; I would add an independent checker. Message text is
  template-based, so the data is not suitable for evaluating NLP models.
- **Not independently validated:** realism of the SLA targets, rating distribution and escalation rates against a
  real institution.

## 5. Verification that does not depend on trusting the AI's claims
Everything claimed in the docs is reproducible with the commands in the README: the structural validator
(`validate`), detector scoring (`evaluate`), SQL queries that independently reproduce four of the five injected anomaly counts,
and the two-run + manifest checksum comparison (`repro-check`).
