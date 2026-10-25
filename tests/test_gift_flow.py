import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gift_scraper.approval import ApprovalGate, GiftPlanner
from gift_scraper.demo import build_demo_inventory, build_demo_plan
from gift_scraper.ecobot_adapter import adapt_ecobot_search_results
from gift_scraper.inventory_monitor import (
    build_gorgon_payload,
    inspect_listing,
    monitor_once,
)
from gift_scraper.models import GiftCandidate, ReviewStatus
from gift_scraper.registry import add_offer, approve_replacement, attach_promo_image


class GiftFlowTests(unittest.TestCase):
    def test_pending_candidate_is_not_eligible_until_explicitly_approved(self):
        candidate = GiftCandidate(
            candidate_id="candidate-a",
            title="Halloween party lights",
            category="Party Supplies",
            supplier="AliExpress",
            price=15.0,
            match_score=1.0,
            inventory=5,
        )
        gate = ApprovalGate()

        self.assertFalse(gate.approve(candidate))
        gate.record_approval(candidate, "curator")
        self.assertTrue(gate.approve(candidate))
        self.assertEqual(candidate.reviewed_by, "curator")

    def test_demo_plan_contains_only_approved_in_stock_candidates(self):
        plan = build_demo_plan(theme="halloween", budget=180.0, limit=3)
        included = [item for bundle in plan.bundles for item in bundle.items]

        self.assertGreaterEqual(len(plan.bundles), 1)
        self.assertTrue(included)
        self.assertTrue(all(item.review_status is ReviewStatus.APPROVED for item in included))
        self.assertTrue(all(item.inventory > 0 for item in included))
        self.assertLessEqual(plan.to_dict()["total_bundle_value"], plan.budget)

    def test_budget_is_enforced_across_the_entire_plan(self):
        inventory = build_demo_inventory()
        plan = GiftPlanner(inventory).build_plan(theme="halloween", budget=50.0, limit=3)

        self.assertLessEqual(plan.to_dict()["total_bundle_value"], 50.0)

    def test_no_eligible_candidates_produces_no_empty_fallback_bundle(self):
        candidate = build_demo_inventory()[6]
        plan = GiftPlanner([candidate]).build_plan(theme="halloween", budget=100.0)

        self.assertEqual(plan.bundles, [])

    def test_ecobot_search_results_are_imported_pending_and_inventory_is_not_invented(self):
        candidates = adapt_ecobot_search_results(
            [{
                "platform": "aliexpress",
                "title": "Halloween Party String Lights",
                "price": 12.5,
                "shipping_cost": 2.0,
                "url": "https://example.com/item/123",
                "orders": 500,
            }],
            category="Party Supplies",
            query="halloween party lights",
        )
        candidate = candidates[0]

        self.assertEqual(candidate.price, 14.5)
        self.assertEqual(candidate.inventory, 0)
        self.assertEqual(candidate.review_status, ReviewStatus.PENDING)
        self.assertEqual(candidate.match_score, 1.0)
        self.assertFalse(ApprovalGate().approve(candidate))

    def test_ecobot_import_rejects_invalid_inventory(self):
        with self.assertRaisesRegex(ValueError, "invalid inventory"):
            adapt_ecobot_search_results(
                [{
                    "title": "Halloween lights",
                    "price": 12.5,
                    "url": "https://example.com/item/123",
                    "inventory": True,
                }],
                category="Party Supplies",
                query="halloween lights",
            )

    def test_out_of_stock_gift_is_removed_and_gorgon_receives_replacement_search_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "data" / "gifts.json"
            registry.parent.mkdir()
            registry.write_text(json.dumps({
                "schema_version": 1,
                "gifts": [{
                    "id": "gift-01",
                    "title": "Halloween ghost lights",
                    "offer_url": "https://www.aliexpress.com/item/123.html",
                    "purchase_condition": "Free with qualifying AliExpress order",
                    "status": "active",
                }],
            }), encoding="utf-8")
            sent = []

            result = monitor_once(
                registry,
                root / "data" / "state.json",
                check=lambda _url: "out_of_stock",
                notify=sent.append,
            )

            saved = json.loads(registry.read_text(encoding="utf-8"))["gifts"][0]
            self.assertEqual(saved["status"], "out_of_stock")
            self.assertEqual(result["removed"], ["gift-01"])
            self.assertEqual(len(sent), 1)
            self.assertEqual(len(sent[0]["alerts"]), 1)
            self.assertIn("https://www.aliexpress.com/w/wholesale-", sent[0]["alerts"][0]["message"])
            self.assertEqual(sent[0]["stats"]["active"], 0)

    def test_captcha_or_unknown_status_never_removes_a_gift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "gifts.json"
            registry.write_text(json.dumps({
                "schema_version": 1,
                "gifts": [{
                    "id": "gift-01",
                    "title": "Halloween ghost lights",
                    "offer_url": "https://www.aliexpress.com/item/123.html",
                    "purchase_condition": "Free with qualifying AliExpress order",
                    "status": "active",
                }],
            }), encoding="utf-8")
            sent = []
            result = monitor_once(
                registry,
                root / "state.json",
                check=lambda _url: "blocked",
                notify=sent.append,
            )
            self.assertEqual(result["removed"], [])
            self.assertEqual(
                json.loads(registry.read_text(encoding="utf-8"))["gifts"][0]["status"],
                "active",
            )
            self.assertEqual(sent[0]["alerts"][0]["type"], "warning")
            self.assertIn("remains active", sent[0]["alerts"][0]["message"])

    def test_failed_gorgon_notification_is_queued_and_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "gifts.json"
            registry.write_text(json.dumps({
                "schema_version": 1,
                "gifts": [{
                    "id": "gift-01",
                    "title": "Halloween ghost lights",
                    "offer_url": "https://www.aliexpress.com/item/123.html",
                    "purchase_condition": "Free with qualifying AliExpress order",
                    "status": "active",
                }],
            }), encoding="utf-8")
            state = root / "state.json"
            with self.assertRaisesRegex(RuntimeError, "alert remains queued"):
                monitor_once(
                    registry,
                    state,
                    check=lambda _url: "unavailable",
                    notify=lambda _payload: (_ for _ in ()).throw(OSError("offline")),
                )
            payloads = []
            result = monitor_once(
                registry,
                state,
                check=lambda _url: self.fail("Removed gifts must not be rechecked before replacement."),
                notify=payloads.append,
            )
            self.assertTrue(result["gorgon_notified"])
            self.assertEqual(payloads[0]["stats"]["deadLinks"], 1)
            self.assertEqual(len(payloads[0]["alerts"]), 1)
            self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["pending_alerts"], [])

    def test_replacement_requires_approval_then_promo_screenshot_before_reactivation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "data" / "gifts.json"
            registry.parent.mkdir()
            registry.write_text(json.dumps({
                "schema_version": 1,
                "gifts": [{
                    "id": "gift-01",
                    "title": "Old offer",
                    "offer_url": "https://www.aliexpress.com/item/123.html",
                    "purchase_condition": "Free with qualifying order",
                    "status": "out_of_stock",
                }],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "approved replacement"):
                attach_promo_image(registry, gift_id="gift-01", image_path=root / "missing.png")
            replacement = approve_replacement(
                registry,
                gift_id="gift-01",
                title="Replacement offer",
                offer_url="https://www.aliexpress.us/item/456.html",
                purchase_condition="Free with qualifying order",
            )
            self.assertEqual(replacement["status"], "pending_image")
            with self.assertRaisesRegex(ValueError, "does not exist"):
                attach_promo_image(registry, gift_id="gift-01", image_path=root / "missing.png")
            screenshot = root / "promo.png"
            screenshot.write_bytes(b"image")
            active = attach_promo_image(registry, gift_id="gift-01", image_path=screenshot)
            self.assertEqual(active["status"], "active")
            self.assertTrue((root / active["image_path"]).is_file())

    def test_registry_rejects_non_aliexpress_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "gifts.json"
            registry.write_text('{"schema_version":1,"gifts":[]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "AliExpress"):
                add_offer(
                    registry,
                    gift_id="gift-01",
                    title="Not an AliExpress gift",
                    offer_url="https://example.com/item/1",
                    purchase_condition="Free with qualifying order",
                )

    def test_listing_inspection_does_not_mistake_a_challenge_for_stock(self):
        class Response:
            status = 200
            headers = {"Content-Type": "text/html"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self, _size):
                return b"<title>Security verification</title>Are you a robot? Add to cart"

        with patch("urllib.request.OpenerDirector.open", return_value=Response()):
            self.assertEqual(
                inspect_listing("https://www.aliexpress.com/item/123.html"),
                "blocked",
            )


if __name__ == "__main__":
    unittest.main()
