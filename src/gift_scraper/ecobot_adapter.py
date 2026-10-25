from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

from .models import GiftCandidate


def adapt_ecobot_search_results(
    records: Iterable[Mapping[str, Any]],
    *,
    category: str,
    query: str,
) -> list[GiftCandidate]:
    """Convert EcoBot scraper records into unapproved Gift Scraper candidates."""
    if not category.strip():
        raise ValueError("category must not be empty")
    if not query.strip():
        raise ValueError("query must not be empty")

    candidates: list[GiftCandidate] = []
    for index, record in enumerate(records):
        title = str(record.get("title") or "").strip()
        supplier_url = str(record.get("url") or "").strip()
        if not title or not supplier_url:
            raise ValueError(f"EcoBot result {index} is missing a title or URL")

        try:
            price = float(record["price"])
            shipping_cost = float(record.get("shipping_cost") or 0)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"EcoBot result {index} has an invalid price") from exc
        if not math.isfinite(price) or not math.isfinite(shipping_cost) or price < 0 or shipping_cost < 0:
            raise ValueError(f"EcoBot result {index} has an invalid price or shipping cost")

        inventory = record.get("inventory", 0)
        if isinstance(inventory, bool) or not isinstance(inventory, int) or inventory < 0:
            raise ValueError(f"EcoBot result {index} has invalid inventory; use a non-negative integer")

        external_id = str(record.get("product_id") or record.get("id") or "").strip()
        candidate_id = external_id or hashlib.sha256(supplier_url.encode("utf-8")).hexdigest()[:16]
        candidates.append(
            GiftCandidate(
                candidate_id=candidate_id,
                title=title,
                category=category.strip(),
                supplier="AliExpress",
                price=price + shipping_cost,
                match_score=_title_match_score(query, title),
                inventory=inventory,
                supplier_url=supplier_url,
                store_sku=str(record["store_sku"]).strip() if record.get("store_sku") else None,
                tags=[token for token in _tokens(title) if token in _tokens(query)],
            )
        )
    return candidates


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _title_match_score(query: str, title: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    return round(len(query_tokens & _tokens(title)) / len(query_tokens), 4)
