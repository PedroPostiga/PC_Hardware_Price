"""Example read queries for the PC Hardware Price Tracker database.

Run after db_setup.py and seed_fake_data.py:
    python test_queries.py
"""

from __future__ import annotations

import sqlite3

from db_setup import get_connection


def get_product_id(connection: sqlite3.Connection, product_name: str) -> int:
    row = connection.execute("SELECT id FROM products WHERE name = ?", (product_name,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown product: {product_name}")
    return row["id"]


def get_latest_price(connection: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT price, currency, scraped_at FROM price_history WHERE product_id = ? ORDER BY scraped_at DESC LIMIT 1",
        (product_id,),
    ).fetchone()


def get_cheapest_price(connection: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT price, currency, scraped_at FROM price_history WHERE product_id = ? ORDER BY price ASC, scraped_at ASC LIMIT 1",
        (product_id,),
    ).fetchone()


def get_price_history(connection: sqlite3.Connection, product_id: int) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT price, currency, scraped_at FROM price_history WHERE product_id = ? ORDER BY scraped_at ASC",
        (product_id,),
    ).fetchall()


def get_recent_price_delta(connection: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    """Return latest minus previous price; None means fewer than two observations."""
    return connection.execute(
        """
        WITH recent AS (
            SELECT price, currency, scraped_at,
                   ROW_NUMBER() OVER (ORDER BY scraped_at DESC) AS position
            FROM price_history WHERE product_id = ?
        )
        SELECT latest.price AS latest_price, previous.price AS previous_price,
               latest.price - previous.price AS price_delta, latest.currency
        FROM recent AS latest
        JOIN recent AS previous ON previous.position = 2
        WHERE latest.position = 1
        """,
        (product_id,),
    ).fetchone()


def get_build_with_current_total(connection: sqlite3.Connection, build_name: str) -> list[sqlite3.Row]:
    """Return every component and its latest price, plus the build total on every row."""
    return connection.execute(
        """
        WITH latest_prices AS (
            SELECT product_id, price, currency, scraped_at,
                   ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY scraped_at DESC) AS position
            FROM price_history
        ),
        build_items AS (
            SELECT p.name, p.category, lp.price, lp.currency, lp.scraped_at
            FROM builds AS b
            JOIN build_components AS bc ON bc.build_id = b.id
            JOIN products AS p ON p.id = bc.product_id
            LEFT JOIN latest_prices AS lp ON lp.product_id = p.id AND lp.position = 1
            WHERE b.name = ?
        )
        SELECT *, SUM(price) OVER () AS build_current_total FROM build_items ORDER BY category, name
        """,
        (build_name,),
    ).fetchall()


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
