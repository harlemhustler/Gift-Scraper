from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.gift_scraper.approval import ApprovalGate, GiftPlanner
from src.gift_scraper.demo import build_demo_plan
from src.gift_scraper.ecobot_adapter import adapt_ecobot_search_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an approved gift plan for a seasonal storefront demo.")
    parser.add_argument("--theme", default="halloween", help="Seasonal theme name")
    parser.add_argument("--budget", type=float, default=180.0, help="Maximum budget for bundle values")
    parser.add_argument("--limit", type=int, default=3, help="Max items per generated bundle")
    parser.add_argument("--scraped-json", type=Path, help="JSON array exported by an EcoBot scraper")
    parser.add_argument("--category", help="Curated category for imported scraper results")
    parser.add_argument(
        "--approve-candidate",
        action="append",
        default=[],
        help="Explicitly approve an imported candidate ID; repeat for multiple candidates",
    )
    parser.add_argument("--reviewer", help="Name recorded for explicit candidate approvals")
    args = parser.parse_args()

    if args.scraped_json is None:
        if args.approve_candidate:
            parser.error("--approve-candidate can only be used with --scraped-json")
        if args.category or args.reviewer:
            parser.error("--category and --reviewer require --scraped-json")
        plan = build_demo_plan(theme=args.theme, budget=args.budget, limit=args.limit)
        print(json.dumps(plan.to_dict(), indent=2))
        return

    if not args.category:
        parser.error("--category is required with --scraped-json")
    if args.approve_candidate and not args.reviewer:
        parser.error("--reviewer is required when approving candidates")

    try:
        records = json.loads(args.scraped_json.read_text(encoding="utf-8"))
    except OSError as exc:
        parser.error(f"cannot read scraper export: {exc}")
    except json.JSONDecodeError as exc:
        parser.error(f"invalid scraper JSON: {exc}")
    if not isinstance(records, list):
        parser.error("scraper export must contain a JSON array")

    candidates = adapt_ecobot_search_results(records, category=args.category, query=args.theme)
    candidate_ids = {candidate.candidate_id for candidate in candidates}
    unknown_ids = set(args.approve_candidate) - candidate_ids
    if unknown_ids:
        parser.error(f"unknown candidate ID(s): {', '.join(sorted(unknown_ids))}")

    gate = ApprovalGate()
    for candidate in candidates:
        if candidate.candidate_id in args.approve_candidate:
            gate.record_approval(candidate, args.reviewer)
    plan = GiftPlanner(candidates).build_plan(theme=args.theme, budget=args.budget, limit=args.limit)
    print(json.dumps({
        "candidates": [candidate.to_dict() for candidate in candidates],
        "plan": plan.to_dict(),
    }, indent=2))


if __name__ == "__main__":
    main()
