"""Generation parameters. One Config drives both the starter and the full dataset."""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime

DEFAULT_SEED = 20261022


@dataclass(frozen=True)
class Config:
    seed: int = DEFAULT_SEED
    tickets: int = 5000
    articles: int = 200
    messages_per_ticket: float = 4.0     # total messages = round(tickets * this)
    anomaly_rate: float = 0.02           # share of tickets per injected anomaly type
    window_start: date = date(2026, 1, 5)    # ticket creation window
    window_end: date = date(2026, 8, 31)
    as_of: datetime = datetime(2026, 10, 31, 23, 59)   # snapshot instant for derived state

    @property
    def messages(self) -> int:
        return round(self.tickets * self.messages_per_ticket)

    @property
    def policies(self) -> int:
        # 16 categories need >= 1 policy each; 200 articles -> 48 policies (3 per category)
        return max(16, round(self.articles * 0.24))

    @property
    def n_learners(self) -> int:
        return max(40, round(self.tickets * 0.33))

    @property
    def n_instructors(self) -> int:
        return max(10, round(self.tickets * 0.07))

    @property
    def n_acad_admin_requesters(self) -> int:
        return max(4, round(self.tickets * 0.006))

    @property
    def staff_per_tier1_team(self) -> int:
        return max(3, round(self.tickets / 800))

    def validate(self) -> None:
        if self.tickets < 20:
            raise ValueError("tickets must be >= 20")
        if self.articles < self.policies:
            raise ValueError("articles must be >= number of policies "
                             f"({self.policies}); raise --articles")
        if self.messages_per_ticket < 3.2:
            raise ValueError("messages_per_ticket must be >= 3.2 (structural minimum of the workflow)")
        if not 0 <= self.anomaly_rate <= 0.1:
            raise ValueError("anomaly_rate must be within [0, 0.1]")


def rng_for(seed: int, stream: str) -> random.Random:
    """Independent, deterministic RNG per named stream (str seeds are hash-randomisation safe)."""
    return random.Random(f"{seed}:{stream}")
