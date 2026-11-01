# Evaluation report

## Anomaly detection (rule-based detectors on input tables vs ground truth)

| Issue type | Injected | Detected | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|---|---|
| answer_cites_expired_policy | 5 | 5 | 5 | 0 | 0 | 1.0 | 1.0 |
| ticket_routed_to_unauthorized_team | 5 | 5 | 5 | 0 | 0 | 1.0 | 1.0 |
| response_claims_unsupported_fact | 5 | 5 | 5 | 0 | 0 | 1.0 | 1.0 |
| sla_clock_ignores_business_hours | 5 | 5 | 5 | 0 | 0 | 1.0 | 1.0 |
| escalation_not_triggered | 5 | 5 | 5 | 0 | 0 | 1.0 | 1.0 |

Escalations with no documented trigger (over-escalation): **0**

## Acceptance criteria (all data, injected defects included)

| Criterion | % |
|---|---|
| answers_cite_current_sources_pct | 97.84 |
| routing_consistent_pct | 98.0 |
| unresolved_or_ambiguous_escalated_pct | 87.8 |
| article_version_recorded_pct | 100.0 |
| answers_with_at_least_one_citation_pct | 100.0 |

## Generator conformance on clean (non-injected) tickets

- tickets: 225; routing team = expected: 100.0%; priority = expected: 100.0%; escalation decision = expected: 100.0%

## Operations

- tickets: 250; messages/ticket: 4.0; escalation rate: 14.4%; reopen rate: 2.8%; feedback rate: 56.33%; mean rating: 4.63
- by status: {'closed': 249, 'resolved': 1}
- by domain: {'FIN': 59, 'REG': 61, 'ACC': 46, 'IT': 84}
- by priority: {'normal': 165, 'low': 27, 'urgent': 14, 'high': 44}
- escalations by reason: {'human_review_required': 17, 'ambiguity_unresolved': 17, 'no_current_policy': 2}
- resolution codes: {'answered_by_policy': 209, 'resolved_after_escalation': 36, 'closed_no_response': 5}
- mean rating by group: {'clean': 4.62, 'anomalous': 4.778}
- case coverage tags: {'ambiguous': 50, 'urgent_deadline': 10, 'deadline_72h': 18, 'requires_human_escalation': 41, 'conditional_routing_rule': 9, 'version_changed_before_answer': 1, 'outdated_or_withdrawn_policy': 2}

| Priority | Tickets | FR breach % | Resolution breach % | Median FR (min) | P90 FR (min) |
|---|---|---|---|---|---|
| high | 44 | 4.55 | 22.73 | 102 | 193 |
| low | 27 | 0.0 | 11.11 | 351 | 744 |
| normal | 165 | 9.09 | 11.52 | 178 | 466 |
| urgent | 14 | 14.29 | 21.43 | 38 | 83 |
