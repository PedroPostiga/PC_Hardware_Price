"""Scrape current primary prices from PCComponentes.pt into ``price_tracker.db``.

Add real PCComponentes product URLs to the ``products`` table, then run:

    python scraper.py

The normal mode selects up to five PCComponentes URLs from the database.  To
test one existing database product without touching the others, use:

    python scraper.py --url "https://www.pccomponentes.pt/product-slug"

Only prices identified as PCComponentes' main product price are stored.  The
scraper deliberately does not fall back to arbitrary euro amounts on the page,
because those can belong to marketplace sellers or recommended products.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from db_setup import get_connection


LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 20
MIN_REQUEST_DELAY_SECONDS = 2
MAX_REQUEST_DELAY_SECONDS = 5
MAX_PRODUCTS_PER_RUN = 5

# This identifies the script and is intentionally a browser-like, non-default UA.
HEADERS = {
    "User-Agent": (
        "PC-Hardware-Price-Tracker/1.0 (+https://github.com/your-username/"
        "pc-hardware-price-tracker; educational portfolio project) "
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
}

# Ordered from the most explicit primary-price markers to common semantic markup.
# Do not add a broad page-wide selector here: it can capture marketplace offers.
PRIMARY_PRICE_SELECTORS = (
    "#pdp-price-current",
    "[data-testid='product-price']",
    "[data-testid='main-product-price']",
    "[data-testid='main-price']",
    "[itemprop='offers'] [itemprop='price']",
)


def make_session() -> requests.Session:
    """Create a session which retries temporary server and rate-limit failures."""
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.75,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.headers.update(HEADERS)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def is_pccomponentes_url(url: str) -> bool:
    """Accept pccomponentes.pt and its subdomains, but not lookalike domains."""
    host = (urlparse(url).hostname or "").lower()
    return host == "pccomponentes.pt" or host.endswith(".pccomponentes.pt")


def parse_portuguese_price(value: str) -> Decimal | None:
    """Convert strings such as ``1.234,56€`` and ``121,99€`` to Decimal."""
    if not value:
        return None

    normalized = value.replace("\u00a0", " ").strip()
    match = re.search(r"\d[\d.\s]*,\d{1,2}|\d[\d,\s]*\.\d{1,2}|\d+", normalized)
    if not match:
        return None

    number = match.group(0).replace(" ", "")
    if "," in number:
        # Portuguese prices use '.' as the thousands separator and ',' for cents.
        number = number.replace(".", "").replace(",", ".")
    elif number.count(".") > 1:
        # A number without cents such as '1.234.567' is still unambiguous.
        number = number.replace(".", "")

    try:
        return Decimal(number)
    except InvalidOperation:
        return None


def extract_product_name(soup: BeautifulSoup) -> str | None:
    """Return the visible title, with Open Graph metadata as a safe fallback."""
    title = soup.select_one("h1")
    if title and title.get_text(" ", strip=True):
        return title.get_text(" ", strip=True)
    metadata = soup.select_one("meta[property='og:title']")
    return metadata.get("content", "").strip() if metadata else None


def extract_primary_dom_price(soup: BeautifulSoup) -> Decimal | None:
    """Try explicit primary-price elements, never a generic page-wide euro match."""
    for selector in PRIMARY_PRICE_SELECTORS:
        element = soup.select_one(selector)
        if element is None:
            continue
        raw_price = element.get("content") or element.get_text(" ", strip=True)
        price = parse_portuguese_price(raw_price)
        if price is not None:
            return price
    return None


def iter_offers(node: Any) -> list[dict[str, Any]]:
    """Flatten direct and nested JSON-LD offers into seller-level dictionaries."""
    if isinstance(node, list):
        return [offer for item in node for offer in iter_offers(item)]
    if isinstance(node, dict):
        # PCComponentes currently wraps the seller offers in an AggregateOffer.
        # Recurse so we inspect its contained Offer, not aggregate low/high prices.
        nested_offers = node.get("offers")
        if nested_offers is not None:
            nested = iter_offers(nested_offers)
            if nested:
                return nested
        return [node]
    return []


def seller_is_pccomponentes(offer: dict[str, Any]) -> bool:
    seller = offer.get("seller") or offer.get("offeredBy") or {}
    if isinstance(seller, dict):
        seller = seller.get("name", "")
    return "pccomponentes" in str(seller).casefold()


def extract_primary_json_ld_price(soup: BeautifulSoup) -> Decimal | None:
    """Use an offer explicitly sold by PCComponentes in Product JSON-LD, if present."""
    for script in soup.select("script[type='application/ld+json']"):
        try:
            payload = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue

        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph", [node])
            for item in graph if isinstance(graph, list) else [graph]:
                if not isinstance(item, dict) or "product" not in str(item.get("@type", "")).casefold():
                    continue
                for offer in iter_offers(item.get("offers")):
                    if seller_is_pccomponentes(offer):
                        price = parse_portuguese_price(str(offer.get("price", "")))
                        if price is not None:
                            return price
    return None


def extract_product_details(html: str) -> tuple[str | None, Decimal | None]:
    """Extract name and primary PCComponentes price from product-page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    name = extract_product_name(soup)
    price = extract_primary_dom_price(soup) or extract_primary_json_ld_price(soup)
    return name, price


def get_products_to_scrape(
    connection: sqlite3.Connection, limit: int, url: str | None = None
) -> list[sqlite3.Row]:
    """Read target product rows from the database; no duplicate in-code URL list."""
    if url is not None:
        row = connection.execute(
            "SELECT id, name, retailer, url FROM products WHERE url = ?", (url,)
        ).fetchone()
        return [row] if row is not None else []

    return connection.execute(
        """
        SELECT id, name, retailer, url
        FROM products
        WHERE lower(url) LIKE '%pccomponentes.pt%'
        ORDER BY id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def save_price(connection: sqlite3.Connection, product_id: int, price: Decimal) -> None:
    """Save one observation. UTC microseconds keep independently fetched rows distinct."""
    scraped_at = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    connection.execute(
        """
        INSERT INTO price_history (product_id, price, currency, scraped_at)
        VALUES (?, ?, 'EUR', ?)
        ON CONFLICT(product_id, scraped_at) DO UPDATE SET
            price = excluded.price,
            currency = excluded.currency
        """,
        (product_id, float(price), scraped_at),
    )


def scrape_product(session: requests.Session, connection: sqlite3.Connection, product: sqlite3.Row) -> bool:
    """Fetch, validate, extract, and store one product. Failures are logged, not raised."""
    url = product["url"]
    if not is_pccomponentes_url(url):
        LOGGER.warning("Skipping product id=%s: URL is not on PCComponentes.pt: %s", product["id"], url)
        return False

    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as error:
        LOGGER.error("Request failed for product id=%s (%s): %s", product["id"], product["name"], error)
        return False

    if not is_pccomponentes_url(response.url):
        LOGGER.error("Product id=%s redirected outside PCComponentes: %s", product["id"], response.url)
        return False

    scraped_name, price = extract_product_details(response.content)
    if not scraped_name:
        LOGGER.error("No product name found for product id=%s at %s", product["id"], url)
        return False
    if price is None:
        LOGGER.error("No primary PCComponentes price found for product id=%s (%s)", product["id"], scraped_name)
        return False

    save_price(connection, product["id"], price)
    LOGGER.info("Saved %s EUR for product id=%s: %s", price, product["id"], scraped_name)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Track primary PCComponentes.pt product prices.")
    parser.add_argument("--url", help="Scrape one URL already present in the products table.")
    parser.add_argument("--limit", type=int, default=MAX_PRODUCTS_PER_RUN, help="Maximum database products to scrape (default: 5).")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with get_connection() as connection, make_session() as session:
        products = get_products_to_scrape(connection, args.limit, args.url)
        if not products:
            LOGGER.warning("No matching PCComponentes products found in the products table.")
            return

        successes = 0
        for index, product in enumerate(products):
            successes += scrape_product(session, connection, product)
            if index < len(products) - 1:
                delay = random.uniform(MIN_REQUEST_DELAY_SECONDS, MAX_REQUEST_DELAY_SECONDS)
                LOGGER.info("Waiting %.1f seconds before the next request", delay)
                time.sleep(delay)

    LOGGER.info("Finished: %s/%s products successfully recorded", successes, len(products))


if __name__ == "__main__":
    main()
