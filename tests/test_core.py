"""Unit tests: business calendar, documented rules, configuration."""
from datetime import date, datetime, timedelta

import pytest

from campus_support.bizcal import (Calendar, add_business_minutes, business_minutes_between, calendar_24x7, is_open)
from campus_support.config import Config
from campus_support.rules import Context

STD = Calendar("CAL-STD", {d: (540, 1020) for d in range(5)}, frozenset({date(2026, 1, 19)}))
EXT = Calendar("CAL-EXT", {**{d: (480, 1200) for d in range(5)}, 5: (600, 840)}, frozenset())


# ---------------------------------------------------------------- business calendar
def test_add_minutes_inside_window():
    assert add_business_minutes(STD, datetime(2026, 3, 3, 10, 0), 30) == datetime(2026, 3, 3, 10, 30)


def test_add_minutes_rolls_over_close_to_next_open():
    # Tue 16:50 + 20 business minutes -> 10 min today, 10 min Wed morning
    assert add_business_minutes(STD, datetime(2026, 3, 3, 16, 50), 20) == datetime(2026, 3, 4, 9, 10)


def test_weekend_and_holiday_are_skipped():
    # Fri 16:59 + 2 min; Monday 2026-01-19 is a holiday -> Tuesday 09:01
    assert add_business_minutes(STD, datetime(2026, 1, 16, 16, 59), 2) == datetime(2026, 1, 20, 9, 1)


def test_start_outside_hours_counts_from_next_opening():
    assert add_business_minutes(STD, datetime(2026, 3, 7, 12, 0), 0) == datetime(2026, 3, 9, 9, 0)   # Saturday


def test_exact_close_boundary():
    assert add_business_minutes(STD, datetime(2026, 3, 3, 16, 0), 60) == datetime(2026, 3, 3, 17, 0)
    assert business_minutes_between(STD, datetime(2026, 3, 3, 16, 0), datetime(2026, 3, 3, 17, 0)) == 60
    assert is_open(STD, datetime(2026, 3, 3, 9, 0)) and not is_open(STD, datetime(2026, 3, 3, 17, 0))


def test_elapsed_is_inverse_of_add():
    start = datetime(2026, 3, 6, 15, 17)
    for m in (1, 59, 480, 2400, 4800):
        assert business_minutes_between(STD, start, add_business_minutes(STD, start, m)) == m


def test_between_zero_when_reversed_or_closed():
    assert business_minutes_between(STD, datetime(2026, 3, 3, 12), datetime(2026, 3, 3, 11)) == 0
    assert business_minutes_between(STD, datetime(2026, 3, 7, 9), datetime(2026, 3, 8, 17)) == 0


def test_extended_calendar_has_saturday_hours():
    assert add_business_minutes(EXT, datetime(2026, 3, 6, 19, 30), 60) == datetime(2026, 3, 7, 10, 30)


def test_24x7_ignores_hours_and_differs_from_business_clock():
    t0 = datetime(2026, 3, 6, 16, 0)                       # Friday afternoon
    wall = add_business_minutes(calendar_24x7(), t0, 480)
    biz = add_business_minutes(STD, t0, 480)
    assert wall == t0 + timedelta(minutes=480) and biz > wall + timedelta(hours=24)


# ---------------------------------------------------------------- rules
def test_routing_conditional_rule_beats_generic(ctx):
    d = date(2026, 3, 3)
    generic = ctx.route("CAT-IT-02", "ROLE-LEARNER", d)
    cond = ctx.route("CAT-IT-02", "ROLE-INSTRUCTOR", d)
    assert generic["priority_override"] is None and cond["priority_override"] == "high"
    assert cond["precedence"] > generic["precedence"] and cond["target_team_id"] == "TEAM-IT"


def test_priority_rule(ctx):
    assert ctx.priority("CAT-FIN-04", None, None) == "normal"
    assert ctx.priority("CAT-FIN-04", 60, None) == "high"          # <=72h bumps one level
    assert ctx.priority("CAT-FIN-04", 24, None) == "urgent"        # <=24h is urgent (boundary inclusive)
    assert ctx.priority("CAT-REG-03", 24.01, None) == "normal"     # low -> normal just outside 24h
    rule = ctx.route("CAT-IT-02", "ROLE-INSTRUCTOR", date(2026, 3, 3))
    assert ctx.priority("CAT-IT-02", None, rule) == "high"


def test_escalation_reasons(ctx):
    assert ctx.escalation_reasons("CAT-IT-01", "matched", None) == []
    assert ctx.escalation_reasons("CAT-FIN-03", "matched", None) == ["human_review_required"]
    assert ctx.escalation_reasons("CAT-IT-01", "no_current_policy", None) == ["no_current_policy"]
    assert ctx.escalation_reasons("CAT-IT-01", "low_confidence", None) == ["ambiguity_unresolved"]
    assert ctx.escalation_reasons("CAT-REG-01", "matched", 24.0) == ["urgent_deadline"]      # boundary inclusive
    assert ctx.escalation_reasons("CAT-REG-01", "matched", 24.5) == []
    assert ctx.escalation_reasons("CAT-IT-01", "matched", 2.0) == []                         # not deadline-sensitive
    assert Context.retrieval_outcome(True, 0.45) == "matched" and Context.retrieval_outcome(True, 0.449) == "low_confidence"
    assert Context.retrieval_outcome(False, 0.99) == "no_current_policy"


def test_effective_article_date_boundaries_are_inclusive(ctx):
    pid = next(p for p, v in ctx.versions.items() if len(v) >= 2)
    v1, v2 = ctx.versions[pid][0], ctx.versions[pid][1]
    assert ctx.effective_article(pid, v2["effective_from"])["version_no"] == 2
    assert ctx.effective_article(pid, v2["effective_from"] - timedelta(days=1))["version_no"] == 1
    assert ctx.effective_article(pid, v1["effective_to"])["version_no"] == 1
    assert ctx.effective_article(pid, v1["effective_from"] - timedelta(days=1)) is None


def test_authorization_matrix(ctx):
    d = date(2026, 3, 3)
    assert ctx.is_authorized("TEAM-FIN", "CAT-FIN-01", d) and ctx.is_authorized("TEAM-ACADADM", "CAT-FIN-01", d)
    assert not ctx.is_authorized("TEAM-IT", "CAT-FIN-01", d) and not ctx.is_authorized("TEAM-PLATFORM", "CAT-REG-01", d)
    assert ctx.is_authorized("TEAM-PLATFORM", "CAT-IT-04", d)


# ---------------------------------------------------------------- config
def test_config_scales_and_limits():
    c = Config()
    assert (c.tickets, c.articles, c.messages, c.policies, c.seed) == (5000, 200, 20000, 48, 20261022)
    Config(tickets=250, articles=40).validate()
    with pytest.raises(ValueError):
        Config(tickets=250, articles=10).validate()          # fewer articles than policies
    with pytest.raises(ValueError):
        Config(messages_per_ticket=2.0).validate()           # below structural minimum
    with pytest.raises(ValueError):
        Config(tickets=5).validate()
