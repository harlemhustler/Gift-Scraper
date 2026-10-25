from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .inventory_monitor import _valid_aliexpress_url, load_gifts


def _save_registry(path: Path, gifts: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"schema_version": 1, "gifts": gifts}, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def add_offer(
    registry_path: Path,
    *,
    gift_id: str,
    title: str,
    offer_url: str,
    purchase_condition: str,
) -> dict[str, Any]:
    gifts = load_gifts(registry_path)
    if not gift_id.strip() or any(gift["id"] == gift_id for gift in gifts):
        raise ValueError("Gift ID must be non-empty and unique.")
    if not title.strip() or not purchase_condition.strip():
        raise ValueError("Title and verified free-with-purchase condition are required.")
    if not _valid_aliexpress_url(offer_url):
        raise ValueError("Offer URL must be HTTPS on an AliExpress domain.")
    gift = {
        "id": gift_id.strip(),
        "title": title.strip(),
        "offer_url": offer_url,
        "purchase_condition": purchase_condition.strip(),
        "status": "active",
    }
    gifts.append(gift)
    _save_registry(registry_path, gifts)
    return gift


def approve_replacement(
    registry_path: Path,
    *,
    gift_id: str,
    title: str,
    offer_url: str,
    purchase_condition: str,
) -> dict[str, Any]:
    gifts = load_gifts(registry_path)
    gift = next((item for item in gifts if item["id"] == gift_id), None)
    if gift is None:
        raise ValueError(f"Unknown gift ID: {gift_id}")
    if gift.get("status") not in {"out_of_stock", "unavailable"}:
        raise ValueError("A replacement can only be approved for a removed gift.")
    if not title.strip() or not purchase_condition.strip():
        raise ValueError("Replacement title and verified free-with-purchase condition are required.")
    if not _valid_aliexpress_url(offer_url):
        raise ValueError("Replacement URL must be HTTPS on an AliExpress domain.")
    gift.setdefault("listing_history", []).append(
        {"title": gift["title"], "offer_url": gift["offer_url"], "status": gift["status"]}
    )
    gift.update(
        {
            "title": title.strip(),
            "offer_url": offer_url,
            "purchase_condition": purchase_condition.strip(),
            "status": "pending_image",
            "image_path": None,
        }
    )
    _save_registry(registry_path, gifts)
    return gift


def attach_promo_image(registry_path: Path, *, gift_id: str, image_path: Path) -> dict[str, Any]:
    gifts = load_gifts(registry_path)
    gift = next((item for item in gifts if item["id"] == gift_id), None)
    if gift is None:
        raise ValueError(f"Unknown gift ID: {gift_id}")
    if gift.get("status") not in {"active", "pending_image"}:
        raise ValueError("Only an active offer or an approved replacement can receive a promo image.")
    if not image_path.is_file():
        raise ValueError(f"Promo image does not exist: {image_path}")
    if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Promo image must be PNG, JPEG, or WebP.")
    image_dir = registry_path.parent / "promo_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    destination = image_dir / f"{gift_id}{image_path.suffix.lower()}"
    shutil.copyfile(image_path, destination)
    gift["image_path"] = destination.relative_to(registry_path.parent.parent).as_posix()
    if gift.get("status") == "pending_image":
        gift["status"] = "active"
    _save_registry(registry_path, gifts)
    return gift
