"""Example read queries for the PC Hardware Price Tracker database.

Run after db_setup.py and seed_fake_data.py:
    python test_queries.py
"""

from __future__ import annotations

from db_setup import get_connection
from queries import (
    get_build_with_current_total,
    get_cheapest_price,
    get_latest_price,
    get_price_history,
    get_product_id,
    get_recent_price_delta,
)


def main() -> None:
    product_name = "AMD Radeon RX 7800 XT 16GB"
    build_name = "Balanced Gaming Build"
    with get_connection() as connection:
        product_id = get_product_id(connection, product_name)
        print(f"Product: {product_name}\n")
        print("Latest price:", dict(get_latest_price(connection, product_id) or {}))
        print("Cheapest recorded price:", dict(get_cheapest_price(connection, product_id) or {}))
        print("Price history:")
        for row in get_price_history(connection, product_id):
            print(" ", dict(row))
        print("Most recent price delta:", dict(get_recent_price_delta(connection, product_id) or {}))
        print(f"\nBuild: {build_name}")
        for row in get_build_with_current_total(connection, build_name):
            print(" ", dict(row))


if __name__ == "__main__":
    main()
