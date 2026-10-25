from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import GiftBundle, GiftCandidate, GiftPlan, ReviewStatus


class ApprovalGate:
    def __init__(self, minimum_score: float = 0.72, minimum_inventory: int = 1):
        self.minimum_score = minimum_score
        self.minimum_inventory = minimum_inventory

    def score_candidate(self, candidate: GiftCandidate) -> float:
        score = (candidate.match_score * 0.7) + (candidate.affordability_score * 0.2)
        inventory_bonus = 0.1 if candidate.inventory >= self.minimum_inventory else 0.0
        return max(0.0, min(1.0, score + inventory_bonus))

    def approve(self, candidate: GiftCandidate) -> bool:
        if candidate.review_status is not ReviewStatus.APPROVED:
            return False
        if candidate.inventory < self.minimum_inventory:
            return False
        if candidate.match_score < self.minimum_score:
            return False
        return self.score_candidate(candidate) >= self.minimum_score

    def record_approval(self, candidate: GiftCandidate, reviewer: str) -> None:
        reviewer = reviewer.strip()
        if not reviewer:
            raise ValueError("reviewer must not be empty")
        candidate.review_status = ReviewStatus.APPROVED
        candidate.reviewed_by = reviewer

    def record_rejection(self, candidate: GiftCandidate, reviewer: str) -> None:
        reviewer = reviewer.strip()
        if not reviewer:
            raise ValueError("reviewer must not be empty")
        candidate.review_status = ReviewStatus.REJECTED
        candidate.reviewed_by = reviewer


class GiftPlanner:
    def __init__(self, candidates: Iterable[GiftCandidate], minimum_score: float = 0.72):
        self.candidates = list(candidates)
        self.gate = ApprovalGate(minimum_score=minimum_score)

    def _group_by_category(self, candidates: Iterable[GiftCandidate]):
        grouped = defaultdict(list)
        for candidate in candidates:
            grouped[candidate.category].append(candidate)
        return grouped

    def build_plan(self, theme: str, budget: float, limit: int = 3) -> GiftPlan:
        if budget < 0:
            raise ValueError("budget must not be negative")
        if limit < 1:
            raise ValueError("limit must be at least one")

        approved = [candidate for candidate in self.candidates if self.gate.approve(candidate)]
        ranked = sorted(
            approved,
            key=lambda item: (self.gate.score_candidate(item), item.match_score),
            reverse=True,
        )
        selected: list[GiftCandidate] = []
        category_counts: dict[str, int] = defaultdict(int)
        remaining_budget = budget
        for candidate in ranked:
            if category_counts[candidate.category] >= limit or candidate.price > remaining_budget:
                continue
            selected.append(candidate)
            category_counts[candidate.category] += 1
            remaining_budget = round(remaining_budget - candidate.price, 2)

        bundles = [
            GiftBundle(name=f"{category} Bundle", category=category, items=items)
            for category, items in self._group_by_category(selected).items()
        ]

        return GiftPlan(theme=theme, budget=budget, bundles=bundles)
