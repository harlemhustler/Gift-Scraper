from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GIFTS = ROOT / "data" / "gifts.json"
DEFAULT_STATE = ROOT / "data" / "gift_inventory_state.json"
DEFAULT_GORGON_URL = "https://api.g0rg0nit3.com/api/inventory/update"
MAX_PAGE_BYTES = 5 * 1024 * 1024

OUT_OF_STOCK = re.compile(
    r"\b(?:out of stock|sold out|currently unavailable|"
    r"this product is no longer available|item is unavailable)\b",
    re.IGNORECASE,
)
IN_STOCK = re.compile(r"\b(?:add to cart|buy now)\b", re.IGNORECASE)
CHALLENGE = re.compile(
    r"\b(?:captcha|recaptcha|verify you are human|are you a robot|"
    r"robot check|security verification)\b",
    re.IGNORECASE,
)


class _StockSignalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[tuple[str, bool, bool]] = []
        self._stock_depth = 0
        self._challenge_depth = 0
        self.stock_text: list[str] = []
        self.challenge_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        stock_marker = tag in {"title", "h1", "button"} or attributes.get("role") == "alert"
        challenge_marker = tag in {"title", "h1", "button", "div", "p"}
        self._stack.append((tag, stock_marker, challenge_marker))
        self._stock_depth += stock_marker
        self._challenge_depth += challenge_marker

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                removed = self._stack[index:]
                self._stack = self._stack[:index]
                self._stock_depth = max(0, self._stock_depth - sum(item[1] for item in removed))
                self._challenge_depth = max(0, self._challenge_depth - sum(item[2] for item in removed))
                break

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._stock_depth:
            self.stock_text.append(text)
        if self._challenge_depth:
            self.challenge_text.append(text)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _valid_aliexpress_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urllib.parse.urlparse(value)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and (host == "aliexpress.com" or host.endswith(".aliexpress.com") or
             host == "aliexpress.us" or host.endswith(".aliexpress.us"))
        and not parsed.username
        and not parsed.password
    )


class _AliExpressRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, new_url):
        if not _valid_aliexpress_url(new_url):
            raise urllib.error.URLError("AliExpress redirected outside its allowed domains.")
        return super().redirect_request(req, fp, code, msg, headers, new_url)


def load_gifts(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"Gift registry does not exist: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"Gift registry contains invalid JSON: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Gift registry must use schema_version 1.")
    gifts = payload.get("gifts")
    if not isinstance(gifts, list):
        raise ValueError("Gift registry 'gifts' must be a list.")
    seen_ids: set[str] = set()
    for gift in gifts:
        if not isinstance(gift, dict):
            raise ValueError("Each gift registry entry must be an object.")
        gift_id = gift.get("id")
        if not isinstance(gift_id, str) or not gift_id.strip() or gift_id in seen_ids:
            raise ValueError("Gift IDs must be non-empty and unique.")
        seen_ids.add(gift_id)
        if not isinstance(gift.get("title"), str) or not gift["title"].strip():
            raise ValueError(f"{gift_id}: a title is required.")
        if not _valid_aliexpress_url(gift.get("offer_url")):
            raise ValueError(f"{gift_id}: offer_url must be an HTTPS AliExpress URL.")
        if gift.get("status", "active") not in {
            "active", "out_of_stock", "unavailable", "pending_image"
        }:
            raise ValueError(f"{gift_id}: unsupported gift status.")
    return gifts


def inspect_listing(url: str, timeout: int = 20) -> str:
    """Check a public listing without solving or working around access challenges."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "EcoPlugGiftInventoryMonitor/1.0 (hourly public listing check)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        opener = urllib.request.build_opener(_AliExpressRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type.lower():
                return "unverified"
            page = response.read(MAX_PAGE_BYTES + 1)
            if len(page) > MAX_PAGE_BYTES:
                return "unverified"
            text = page.decode("utf-8", errors="replace")
            parser = _StockSignalParser()
            parser.feed(text)
            signal_text = " ".join(parser.stock_text)
            challenge_text = " ".join(parser.challenge_text)
            if CHALLENGE.search(challenge_text):
                return "blocked"
            if OUT_OF_STOCK.search(signal_text):
                return "out_of_stock"
            if IN_STOCK.search(signal_text):
                return "in_stock"
            return "unverified"
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            return "unavailable"
        if exc.code in (401, 403, 407, 429):
            return "blocked"
        return "unverified"
    except (TimeoutError, urllib.error.URLError, OSError):
        return "unverified"


def alternatives_url(title: str) -> str:
    query = urllib.parse.quote_plus(f"{title} Halloween gift")
    return f"https://www.aliexpress.com/w/wholesale-{query.replace('+', '-')}.html"


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "last_check": None, "gifts": {}, "pending_alerts": []}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Inventory state contains invalid JSON: {path}") from exc
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("Inventory state must use schema_version 1.")
    if not isinstance(state.get("gifts"), dict) or not isinstance(state.get("pending_alerts"), list):
        raise ValueError("Inventory state has an invalid shape.")
    return state


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _out_of_stock_alert(gift: dict[str, Any], checked_at: str) -> dict[str, Any]:
    search_url = alternatives_url(gift["title"])
    message = (
        f"AliExpress gift offer is out of stock or unavailable and was removed from the active gift pool: "
        f"{gift['title']} ({gift['id']}). Original offer: {gift['offer_url']}. "
        f"Find a replacement here: {search_url}. Confirm it is a free-with-purchase offer. "
        "After you approve the replacement, provide its promo image; it will not become active before then."
    )
    return {
        "type": "error",
        "message": message,
        "timestamp": checked_at,
    }


def build_gorgon_payload(
    gifts: list[dict[str, Any]],
    statuses: dict[str, str],
    alerts: list[dict[str, Any]],
    checked_at: str,
) -> dict[str, Any]:
    active = [gift for gift in gifts if gift.get("status", "active") == "active"]
    out_of_stock = sum(
        gift.get("status") == "out_of_stock" or statuses.get(gift["id"]) == "out_of_stock"
        for gift in gifts
    )
    unavailable = sum(
        gift.get("status") == "unavailable" or statuses.get(gift["id"]) == "unavailable"
        for gift in gifts
    )
    return {
        "lastCheck": checked_at,
        "products": [
            {
                "sku": gift["id"],
                "url": gift["offer_url"],
                "status": (
                    "active"
                    if statuses.get(gift["id"], "active") == "in_stock"
                    else "unverified"
                ),
                "message": (
                    gift["title"]
                    if statuses.get(gift["id"], "active") == "in_stock"
                    else f"{gift['title']} - check status: {statuses.get(gift['id'], 'unverified')}"
                ),
            }
            for gift in active
        ],
        "stats": {
            "total": len(gifts),
            "active": len(active),
            "deadLinks": unavailable,
            "outOfStock": out_of_stock,
            "autoUnpublished": out_of_stock + unavailable,
        },
        "alerts": alerts,
    }


def send_gorgon_alerts(
    payload: dict[str, Any],
    endpoint: str | None = None,
    timeout: int = 15,
) -> None:
    url = endpoint or os.environ.get("GORGON_INVENTORY_URL", DEFAULT_GORGON_URL)
    if not url.startswith("https://"):
        raise ValueError("Gorgon inventory endpoint must use HTTPS.")
    token = os.environ.get("GORGON_INVENTORY_TOKEN")
    if not token or len(token) < 32:
        token_path = os.environ.get("GORGON_INVENTORY_TOKEN_FILE")
        if token_path:
            token = Path(token_path).read_text(encoding="utf-8").strip()
    if not token or len(token) < 32:
        raise ValueError("Set GORGON_INVENTORY_TOKEN or GORGON_INVENTORY_TOKEN_FILE to a 32-character token.")
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Gorgon inventory update failed with HTTP {response.status}.")
        result = json.loads(response.read(64 * 1024).decode("utf-8"))
    if not isinstance(result, dict) or result.get("success") is not True:
        raise RuntimeError("Gorgon did not confirm receipt of the inventory update.")


def monitor_once(
    registry_path: Path = DEFAULT_GIFTS,
    state_path: Path = DEFAULT_STATE,
    *,
    check=inspect_listing,
    notify=send_gorgon_alerts,
) -> dict[str, Any]:
    gifts = load_gifts(registry_path)
    if not gifts:
        raise ValueError("No real AliExpress gift offers are configured; refusing to run an empty monitor.")
    state = _read_state(state_path)
    checked_at = _now()
    statuses: dict[str, str] = {}
    alerts: list[dict[str, Any]] = []
    changed = False

    for gift in gifts:
        if gift.get("status", "active") != "active":
            continue
        status = check(gift["offer_url"])
        statuses[gift["id"]] = status
        record = state["gifts"].setdefault(gift["id"], {})
        record.update({"last_status": status, "last_checked": checked_at})
        if status in {"out_of_stock", "unavailable"}:
            gift["status"] = status
            gift["removed_at"] = checked_at
            record["removed_at"] = checked_at
            alert = _out_of_stock_alert(gift, checked_at)
            alert["id"] = f"{gift['id']}:{status}"
            if not any(item.get("id") == alert["id"] for item in state["pending_alerts"]):
                state["pending_alerts"].append(alert)
            changed = True
        elif status in {"blocked", "unverified"}:
            warning = {
                "type": "warning",
                "message": (
                    f"Could not verify AliExpress stock for {gift['title']} ({gift['id']}); "
                    f"the gift remains active pending a check. Listing: {gift['offer_url']}"
                ),
                "timestamp": checked_at,
                "id": f"{gift['id']}:verification",
            }
            alerts.append(warning)

    state["last_check"] = checked_at
    _write_json(state_path, state)
    _write_json(registry_path, {"schema_version": 1, "gifts": gifts})
    payload = build_gorgon_payload(gifts, statuses, alerts, checked_at)

    payload["alerts"] = state["pending_alerts"] + alerts
    try:
        notify(payload)
    except Exception as exc:
        state["last_gorgon_error"] = f"{type(exc).__name__}: {exc}"
        _write_json(state_path, state)
        raise RuntimeError(
            "Gift status was saved locally, but Gorgon did not confirm the alert; "
            "the alert remains queued for the next run."
        ) from exc

    state["pending_alerts"] = []
    state.pop("last_gorgon_error", None)
    _write_json(state_path, state)
    return {
        "checked_at": checked_at,
        "statuses": statuses,
        "removed": [gift["id"] for gift in gifts if gift.get("status") in {"out_of_stock", "unavailable"}],
        "gorgon_notified": True,
        "changed": changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check configured AliExpress gift offers and alert Gorgon.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_GIFTS)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()
    try:
        print(json.dumps(monitor_once(args.registry, args.state), indent=2))
        return 0
    except Exception as exc:
        print(f"Gift inventory monitor failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
