from __future__ import annotations

from .approval import GiftPlanner
from .models import GiftCandidate, ReviewStatus


def build_demo_inventory() -> list[GiftCandidate]:
    return [
        GiftCandidate(
            candidate_id="TH-001",
            title="Glow Pumpkin Table Runner",
            category="Party Supplies",
            supplier="AliExpress",
            price=18.99,
            match_score=0.95,
            inventory=12,
            supplier_url="https://example.com/party-runner",
            review_status=ReviewStatus.APPROVED,
            reviewed_by="demo-curator",
            tags=["halloween", "party", "decor"],
        ),
        GiftCandidate(
            candidate_id="TH-002",
            title="Haunted House String Lights",
            category="Party Supplies",
            supplier="AliExpress",
            price=24.5,
            match_score=0.93,
            inventory=9,
            supplier_url="https://example.com/string-lights",
            review_status=ReviewStatus.APPROVED,
            reviewed_by="demo-curator",
            tags=["lighting", "decor", "party"],
        ),
        GiftCandidate(
            candidate_id="TH-003",
            title="Skeleton Family Costume Set",
            category="Costumes",
            supplier="AliExpress",
            price=34.99,
            match_score=0.9,
            inventory=7,
            supplier_url="https://example.com/costume-set",
            review_status=ReviewStatus.APPROVED,
            reviewed_by="demo-curator",
            tags=["costume", "family"],
        ),
        GiftCandidate(
            candidate_id="TH-004",
            title="Witch Hat and Cape Combo",
            category="Costumes",
            supplier="AliExpress",
            price=21.0,
            match_score=0.88,
            inventory=14,
            supplier_url="https://example.com/witch-set",
            review_status=ReviewStatus.APPROVED,
            reviewed_by="demo-curator",
            tags=["costume", "cape"],
        ),
        GiftCandidate(
            candidate_id="TH-005",
            title="Bluetooth Speaker Bundle",
            category="Electronics",
            supplier="AliExpress",
            price=46.75,
            match_score=0.97,
            inventory=6,
            supplier_url="https://example.com/speaker-bundle",
            review_status=ReviewStatus.APPROVED,
            reviewed_by="demo-curator",
            tags=["audio", "party"],
        ),
        GiftCandidate(
            candidate_id="TH-006",
            title="RGB Strobe Party Light",
            category="Electronics",
            supplier="AliExpress",
            price=29.5,
            match_score=0.91,
            inventory=15,
            supplier_url="https://example.com/strobe-light",
            review_status=ReviewStatus.APPROVED,
            reviewed_by="demo-curator",
            tags=["lighting", "electronics"],
        ),
        GiftCandidate(
            candidate_id="TH-007",
            title="Low Fit Costume Match",
            category="Costumes",
            supplier="AliExpress",
            price=16.2,
            match_score=0.51,
            inventory=11,
            supplier_url="https://example.com/low-fit-costume",
            tags=["costume"],
        ),
        GiftCandidate(
            candidate_id="TH-008",
            title="Party Supply Overstock",
            category="Party Supplies",
            supplier="AliExpress",
            price=8.25,
            match_score=0.7,
            inventory=0,
            supplier_url="https://example.com/out-of-stock-party",
            tags=["party", "clearance"],
        ),
    ]


def build_demo_plan(theme: str = "halloween", budget: float = 180.0, limit: int = 3):
    planner = GiftPlanner(build_demo_inventory())
    return planner.build_plan(theme=theme, budget=budget, limit=limit)
