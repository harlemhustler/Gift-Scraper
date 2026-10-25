from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.gift_scraper.inventory_monitor import DEFAULT_GIFTS, load_gifts
from src.gift_scraper.registry import add_offer, approve_replacement, attach_promo_image


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage approved AliExpress free-with-purchase gift offers.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_GIFTS)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="List the configured gift offers.")

    add = commands.add_parser("add", help="Add a manually verified initial gift offer.")
    add.add_argument("--id", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--url", required=True)
    add.add_argument("--condition", required=True, help="Verified AliExpress purchase condition.")

    replace = commands.add_parser("approve-replacement", help="Approve a replacement listing after reviewing it.")
    replace.add_argument("--id", required=True, help="ID of the removed gift to replace.")
    replace.add_argument("--title", required=True)
    replace.add_argument("--url", required=True)
    replace.add_argument("--condition", required=True, help="Verified AliExpress purchase condition.")

    image = commands.add_parser("set-image", help="Attach the approved replacement's promo screenshot.")
    image.add_argument("--id", required=True)
    image.add_argument("--file", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "list":
        print(json.dumps(load_gifts(args.registry), indent=2))
    elif args.command == "add":
        print(json.dumps(add_offer(
            args.registry,
            gift_id=args.id,
            title=args.title,
            offer_url=args.url,
            purchase_condition=args.condition,
        ), indent=2))
    elif args.command == "approve-replacement":
        gift = approve_replacement(
            args.registry,
            gift_id=args.id,
            title=args.title,
            offer_url=args.url,
            purchase_condition=args.condition,
        )
        print(json.dumps(gift, indent=2))
        print(
            "Replacement approved. Now provide the AliExpress promo screenshot with "
            f"`python manage_gifts.py set-image --id {args.id} --file <screenshot.png>`."
        )
    elif args.command == "set-image":
        print(json.dumps(attach_promo_image(
            args.registry,
            gift_id=args.id,
            image_path=args.file,
        ), indent=2))


if __name__ == "__main__":
    main()
