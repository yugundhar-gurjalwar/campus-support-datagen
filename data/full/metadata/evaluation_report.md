# Evaluation report

## Anomaly detection (rule-based detectors on input tables vs ground truth)

| Issue type | Injected | Detected | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|---|---|
| answer_cites_expired_policy | 100 | 100 | 100 | 0 | 0 | 1.0 | 1.0 |
| ticket_routed_to_unauthorized_team | 100 | 100 | 100 | 0 | 0 | 1.0 | 1.0 |
| response_claims_unsupported_fact | 100 | 100 | 100 | 0 | 0 | 1.0 | 1.0 |
| sla_clock_ignores_business_hours | 100 | 100 | 100 | 0 | 0 | 1.0 | 1.0 |
| escalation_not_triggered | 100 | 100 | 100 | 0 | 0 | 1.0 | 1.0 |

Escalations with no documented trigger (over-escalation): **0**

## Acceptance criteria (all data, injected defects included)

| Criterion | % |
|---|---|
| answers_cite_current_sources_pct | 97.81 |
| routing_consistent_pct | 98.0 |
| unresolved_or_ambiguous_escalated_pct | 89.94 |
| article_version_recorded_pct | 100.0 |
| answers_with_at_least_one_citation_pct | 100.0 |

## Generator conformance on clean (non-injected) tickets

- tickets: 4500; routing team = expected: 100.0%; priority = expected: 100.0%; escalation decision = expected: 100.0%

## Operations

- tickets: 5000; messages/ticket: 4.0; escalation rate: 17.88%; reopen rate: 3.38%; feedback rate: 55.66%; mean rating: 4.55
- by status: {'closed': 4965, 'in_progress': 5, 'resolved': 24, 'pending_requester': 6}
- by domain: {'ACC': 676, 'IT': 1617, 'FIN': 1369, 'REG': 1338}
- by priority: {'urgent': 270, 'normal': 3395, 'low': 571, 'high': 764}
- escalations by reason: {'ambiguity_unresolved': 280, 'human_review_required': 407, 'urgent_deadline': 60, 'no_current_policy': 147}
- resolution codes: {'answered_by_policy': 3957, 'resolved_after_escalation': 890, 'closed_no_response': 142, 'open': 11}
- mean rating by group: {'clean': 4.588, 'anomalous': 4.191}
- case coverage tags: {'urgent_deadline': 247, 'ambiguous': 957, 'requires_human_escalation': 994, 'deadline_72h': 282, 'conditional_routing_rule': 156, 'version_changed_before_answer': 22, 'outdated_or_withdrawn_policy': 147}

| Priority | Tickets | FR breach % | Resolution breach % | Median FR (min) | P90 FR (min) |
|---|---|---|---|---|---|
| high | 764 | 6.15 | 25.26 | 83 | 199 |
| low | 571 | 6.65 | 11.21 | 329 | 787 |
| normal | 3395 | 8.1 | 13.67 | 173 | 437 |
| urgent | 270 | 5.19 | 34.07 | 32 | 48 |
