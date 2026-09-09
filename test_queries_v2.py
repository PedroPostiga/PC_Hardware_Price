"""Seed the database and print reusable-query results for a quick sanity check.

Run with:
    python test_queries_v2.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from db_setup import get_connection
from queries import (
    get_all_time_price_range,
    get_average_price,
    get_percent_change,
    get_product_id,
    get_products_at_or_below_target,
)
from seed_fake_data import seed_database


def print_row(label: str, row: object) -> None:
    print(f"{label}: {dict(row) if row is not None else 'None'}")


def main() -> None:
    # Makes the script runnable from a fresh Phase 1 database without duplicates.
    seed_database()
    product_name = "AMD Radeon RX 7800 XT 16GB"
    # The latest seeded record is 2026-04-01. This fixed report date makes the
    # 30-day average deterministic and easy to verify by hand.
    report_date = datetime(2026, 4, 1, 10, tzinfo=timezone.utc)

    with get_connection() as connection:
        product_id = get_product_id(connection, product_name)
        print(f"Product: {product_name}\n")
        print_row("30-day average", get_average_price(connection, product_id, days=30, as_of=report_date))
        print_row("30-day percent change", get_percent_change(connection, product_id, days=30))
        print_row("All-time price range", get_all_time_price_range(connection, product_id))
        print("\nProducts at or below target:")
        for row in get_products_at_or_below_target(connection):
            print(" ", dict(row))

        # Demonstrate explicit no-history/no-window behavior without persisting a row.
        temporary_url = f"https://www.pccomponentes.pt/query-edge-case-{uuid4()}"
        temporary_id = connection.execute(
            "INSERT INTO products (name, category, retailer, url) VALUES (?, ?, ?, ?)",
            ("Temporary query edge case", "CPU", "PCComponentes.pt", temporary_url),
        ).lastrowid
        print("\nNo-history product edge cases:")
        print_row("Average", get_average_price(connection, temporary_id, days=30, as_of=report_date))
        print_row("Percent change", get_percent_change(connection, temporary_id, days=30))
        print_row("All-time range", get_all_time_price_range(connection, temporary_id))
        empty_window_date = datetime(2026, 2, 25, 10, tzinfo=timezone.utc)
        print_row(
            "No-observation window",
            get_average_price(connection, product_id, days=7, as_of=empty_window_date),
        )
        connection.rollback()  # Remove only the temporary edge-case row.


if __name__ == "__main__":
    main()
