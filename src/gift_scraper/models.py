from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class GiftCandidate:
    candidate_id: str
    title: str
    category: str
    supplier: str
    price: float
    match_score: float
    inventory: int
    supplier_url: str | None = None
    store_sku: str | None = None
    review_status: ReviewStatus = ReviewStatus.PENDING
    reviewed_by: str | None = None
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must not be empty")
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.category.strip():
            raise ValueError("category must not be empty")
        if not self.supplier.strip():
            raise ValueError("supplier must not be empty")
        if self.price < 0:
            raise ValueError("price must not be negative")
        if not 0 <= self.match_score <= 1:
            raise ValueError("match_score must be between 0 and 1")
        if self.inventory < 0:
            raise ValueError("inventory must not be negative")

    @property
    def affordability_score(self) -> float:
        if self.price <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 / self.price * 10.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "title": self.title,
            "category": self.category,
            "supplier": self.supplier,
            "price": round(self.price, 2),
            "match_score": round(self.match_score, 2),
            "inventory": self.inventory,
            "supplier_url": self.supplier_url,
            "store_sku": self.store_sku,
            "review_status": self.review_status.value,
            "reviewed_by": self.reviewed_by,
            "tags": self.tags,
        }


@dataclass
class GiftBundle:
    name: str
    category: str
    items: list[GiftCandidate]

    @property
    def total_price(self) -> float:
        return round(sum(item.price for item in self.items), 2)

    @property
    def average_match(self) -> float:
        if not self.items:
            return 0.0
        return round(sum(item.match_score for item in self.items) / len(self.items), 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "items": [item.to_dict() for item in self.items],
            "total_price": self.total_price,
            "average_match": self.average_match,
        }


@dataclass
class GiftPlan:
    theme: str
    budget: float
    bundles: list[GiftBundle]

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "budget": round(self.budget, 2),
            "bundles": [bundle.to_dict() for bundle in self.bundles],
            "total_bundle_value": round(sum(bundle.total_price for bundle in self.bundles), 2),
        }
