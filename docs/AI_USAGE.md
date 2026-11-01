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

## 4. What the candidate personally reviewed, changed and validated — **TO COMPLETE BEFORE SUBMISSION**
> **Independent SQL cross-check:** I loaded the generated SQL into SQLite and ran the four README queries. They
  returned [100 each on the full dataset / 5 each on the starter dataset]. This matches the injected counts in
  `ground_truth_anomalies.csv`, so the anomalies can be found with plain SQL and don't depend on the Python
  detectors. The fifth type (escalation not triggered) has no SQL query and relies on the Python detector.

## 5. Verification that does not depend on trusting the AI's claims
Everything claimed in the docs is reproducible with the commands in the README: the structural validator
(`validate`), detector scoring (`evaluate`), SQL queries that independently reproduce four of the five injected anomaly counts,
and the two-run + manifest checksum comparison (`repro-check`).
