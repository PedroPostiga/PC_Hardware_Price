"""Add one PCComponentes product to the local price tracker database.

Example:
    python add_product.py --name "AMD Ryzen 5 7600" --category CPU \
        --retailer PCComponentes.pt \
        --url "https://www.pccomponentes.pt/product-slug" --target-price 180
"""

from __future__ import annotations

import argparse

from db_setup import get_connection
from scraper import is_pccomponentes_url


def parse_target_price(value: str) -> float:
    """Accept a non-negative target price from the command line."""
    try:
        price = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("target price must be a number") from error
    if price < 0:
        raise argparse.ArgumentTypeError("target price cannot be negative")
    return price


def add_product(
    name: str, category: str, retailer: str, url: str, target_price: float | None
) -> bool:
    """Insert a product, returning True only when a new row was created."""
    if not is_pccomponentes_url(url):
        raise ValueError("URL must be on pccomponentes.pt (for example https://www.pccomponentes.pt/...)")

    with get_connection() as connection:
        result = connection.execute(
            """
            INSERT INTO products (name, category, retailer, url, target_price)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(retailer, url) DO NOTHING
            """,
            (name.strip(), category.strip(), retailer.strip(), url.strip(), target_price),
        )
    return result.rowcount == 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a PCComponentes product to track.")
    parser.add_argument("--name", required=True, help="Product name")
    parser.add_argument("--category", required=True, help="Category, such as GPU, CPU, or RAM")
    parser.add_argument("--retailer", required=True, help="Retailer label, such as PCComponentes.pt")
    parser.add_argument("--url", required=True, help="Bare PCComponentes product URL")
    parser.add_argument("--target-price", type=parse_target_price, help="Optional target price in EUR")
    args = parser.parse_args()

    try:
        inserted = add_product(args.name, args.category, args.retailer, args.url, args.target_price)
    except ValueError as error:
        parser.error(str(error))

    if inserted:
        print(f"Added: {args.name}")
    else:
        print("Not added: a product with this retailer and URL already exists.")


if __name__ == "__main__":
    main()
