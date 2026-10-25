# Gift Scraper Rebuild

This project is the rebuilt foundation for EcoPlug's AliExpress free-with-purchase gift workflow. Freebie offers are tracked separately from regular Shopify merchandise: only manually verified AliExpress offer URLs and purchase conditions enter the registry. The monitor never buys inventory or silently substitutes gifts.

## What this rebuild does
- Accepts product records exported by EcoBot's AliExpress scraper through a small, network-free adapter.
- Scores title relevance, estimates landed supplier cost, and keeps every imported listing pending until explicit review.
- Tracks product category fit for Party Supplies, Costumes, and Electronics bundles.
- Requires explicit human approval, numeric in-stock inventory, and a sufficiently high match score before a product can enter a plan.
- Produces bundle plans that can be used as the backend contract for a storefront demo or an internal planner.
- Checks configured AliExpress gift offers hourly using ordinary public listing requests.
- Removes an offer from the active gift pool only after explicit out-of-stock or unavailable evidence; CAPTCHA, access denial, and ambiguous pages remain unverified.
- Sends Gorgon an authenticated inventory update with a replacement search link, and queues alerts locally if Gorgon is unavailable.
- Keeps a replacement inactive until it is explicitly approved and its promo screenshot is attached.

## Project structure

```text
Gift Scraper PROJECT/
├── app.py
├── manage_gifts.py
├── install_hourly_monitor.ps1
├── data/
│   └── gifts.json
├── README.md
├── src/
│   └── gift_scraper/
│       ├── __init__.py
│       ├── approval.py
│       ├── demo.py
│       ├── ecobot_adapter.py
│       ├── inventory_monitor.py
│       └── models.py
├── tests/
│   └── test_gift_flow.py
└── Bot Log/
    └── session logs
```

## Safe operating model
- This is a planning and validation layer for approved gift inventory, not a live order engine.
- Imported EcoBot search records are always pending review; the source scraper's "orders" count is never treated as inventory.
- Inventory must be supplied as a non-negative integer in the imported record, and candidate approval must be explicitly recorded by a named reviewer.
- The total price of all selected bundles cannot exceed the plan budget.
- AliExpress pages that require CAPTCHA or block automated access are not bypassed. The monitor reports them as unverified and does not remove gifts based on that result.
- Gift checks are not supplier stock guarantees or purchase actions. The free-with-purchase condition must be reviewed on AliExpress and recorded with each gift.
- Gorgon alerts require a 32-character `GORGON_INVENTORY_TOKEN` on its backend and a private `GORGON_INVENTORY_TOKEN_FILE` path for this monitor.
- A detected gift is soft-deactivated in the local registry; its audit history is retained. No Shopify products, prices, discounts, or supplier orders are modified.

## Quick start

```bash
cd "A Hustler's Guide To Prompt Engineering\Gift Scraper PROJECT"
python app.py --theme halloween --budget 180 --limit 3
python -m unittest discover -s tests -v
```

## Gift inventory monitoring

The committed `data/gifts.json` is intentionally empty; demo examples are not real freebies. Add each real offer only after verifying its free-with-purchase terms on AliExpress:

```powershell
python manage_gifts.py add --id gift-01 --title "Offer title" --url "https://www.aliexpress.com/item/..." --condition "Verified offer terms"
python manage_gifts.py list
```

Configure Gorgon's private inventory token via `GORGON_INVENTORY_TOKEN_FILE`, then run a single check:

```powershell
$env:GORGON_INVENTORY_TOKEN_FILE = "C:\private\gorgon_inventory_token.txt"
python -m src.gift_scraper.inventory_monitor
```

After at least six real offers are in the registry and Gorgon is configured, install the hourly Windows task:

```powershell
.\install_hourly_monitor.ps1
```

On an out-of-stock or unavailable result, the offer is removed from the active pool and Gorgon receives an AliExpress search link. CAPTCHA or an ambiguous page never causes removal. Review the replacement manually, then record approval; the CLI will prompt for its promo screenshot:

```powershell
python manage_gifts.py approve-replacement --id gift-01 --title "Replacement title" --url "https://www.aliexpress.com/item/..." --condition "Verified offer terms"
python manage_gifts.py set-image --id gift-01 --file "C:\path\to\promo-screenshot.png"
```

## Importing EcoBot search results

Export the list returned by EcoBot's `AliExpressScraper.search_products(...)` to a JSON file, then import it without triggering any scraper requests:

```bash
python app.py --theme "halloween party lights" --category "Party Supplies" --scraped-json candidates.json
```

The first run reports candidates as pending and does not plan them. After reviewing each listing, add verified numeric `inventory` to the JSON record and explicitly approve selected IDs with a reviewer name:

```bash
python app.py --theme "halloween party lights" --category "Party Supplies" --scraped-json candidates.json --approve-candidate <candidate-id> --reviewer "Your Name"
```

The adapter uses EcoBot's `title`, `price`, `shipping_cost`, `url`, and optional `inventory` fields. It calculates a title-token match score for review, adds shipping to the listed cost, and never treats AliExpress orders/sold counts as available stock. Listings without verified inventory remain ineligible.

## Intended next phase
- Add the approved screenshot-backed gift list to the storefront and connect it to actual free-with-purchase eligibility.
- Map reviewer-approved products to canonical Shopify SKUs and confirmed DSers variants using EcoBot's fulfillment planner.
- Keep the public storefront demo separate from any live fulfillment or supplier integration.

## Status
The monitor, safe removal/replacement workflow, Gorgon alert client, and hourly task installer are implemented and covered by tests. The six real freebie offers have not been populated, the hourly task has not been installed, and Gorgon is currently unavailable; live monitoring and alerts are therefore not active yet. No AliExpress purchase or Shopify change is performed by this workflow.