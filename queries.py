"""Reusable SQLite query and analysis functions for the price tracker.

All functions accept the connection returned by ``db_setup.get_connection``.
They only read data, so callers control connection lifetime and transactions.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone


def get_product_id(connection: sqlite3.Connection, product_name: str) -> int:
    """Return a product ID by name, or raise ValueError when it does not exist."""
    row = connection.execute("SELECT id FROM products WHERE name = ?", (product_name,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown product: {product_name}")
    return row["id"]


def get_latest_price(connection: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    """Return the most recent price observation, or None when no history exists."""
    return connection.execute(
        "SELECT price, currency, scraped_at FROM price_history WHERE product_id = ? ORDER BY scraped_at DESC LIMIT 1",
        (product_id,),
    ).fetchone()


def get_cheapest_price(connection: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    """Return the cheapest observation, choosing the earliest date to break a tie."""
    return connection.execute(
        "SELECT price, currency, scraped_at FROM price_history WHERE product_id = ? ORDER BY price ASC, scraped_at ASC LIMIT 1",
        (product_id,),
    ).fetchone()


def get_price_history(connection: sqlite3.Connection, product_id: int) -> list[sqlite3.Row]:
    """Return all observations in ascending scrape-time order."""
    return connection.execute(
        "SELECT price, currency, scraped_at FROM price_history WHERE product_id = ? ORDER BY scraped_at ASC",
        (product_id,),
    ).fetchall()


def get_recent_price_delta(connection: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    """Return latest minus previous price, or None when fewer than two rows exist."""
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
    """Return build components and each latest price, with the total repeated per row."""
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


def _window_bounds(days: int, as_of: datetime | None) -> tuple[str, str]:
    """Build UTC ISO-8601 boundaries compatible with the schema timestamps."""
    if days < 1:
        raise ValueError("days must be at least 1")
    reference = as_of or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)
    window_start = reference - timedelta(days=days)
    return (
        window_start.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        reference.isoformat(timespec="microseconds").replace("+00:00", "Z"),
    )


def get_average_price(
    connection: sqlite3.Connection,
    product_id: int,
    days: int = 30,
    *,
    as_of: datetime | None = None,
) -> sqlite3.Row | None:
    """Return price average/count for observations in the inclusive trailing window.

    ``as_of`` is mainly useful for reports and deterministic tests. When omitted,
    the window ends at the current UTC time. Returns None if the window has no
    observations (including when the product has no history).
    """
    window_start, window_end = _window_bounds(days, as_of)
    row = connection.execute(
        """
        SELECT AVG(price) AS average_price,
               COUNT(*) AS observation_count,
               MIN(currency) AS currency,
               ? AS window_start,
               ? AS window_end
        FROM price_history
        -- ``scraped_at`` can contain either whole seconds or microseconds.
        -- julianday() avoids incorrect lexicographic boundary comparisons.
        WHERE product_id = ?
          AND julianday(scraped_at) >= julianday(?)
          AND julianday(scraped_at) <= julianday(?)
        """,
        (window_start, window_end, product_id, window_start, window_end),
    ).fetchone()
    return row if row is not None and row["observation_count"] else None


def get_percent_change(
    connection: sqlite3.Connection, product_id: int, days: int = 30
) -> sqlite3.Row | None:
    """Return percentage change from the closest observation at least N days old.

    The latest recorded observation anchors the calculation. The baseline is the
    most recent observation at or before ``latest.scraped_at - days``; this avoids
    treating a sparse collection of observations as if it were daily data.
    Returns None if no qualifying baseline exists or that baseline is zero.
    """
    if days < 1:
        raise ValueError("days must be at least 1")
    latest = get_latest_price(connection, product_id)
    if latest is None:
        return None

    latest_time = datetime.fromisoformat(latest["scraped_at"].replace("Z", "+00:00"))
    if latest_time.tzinfo is None:
        latest_time = latest_time.replace(tzinfo=timezone.utc)
    cutoff = (latest_time.astimezone(timezone.utc) - timedelta(days=days)).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    baseline = connection.execute(
        """
        SELECT price, currency, scraped_at
        FROM price_history
        WHERE product_id = ? AND julianday(scraped_at) <= julianday(?)
        ORDER BY scraped_at DESC
        LIMIT 1
        """,
        (product_id, cutoff),
    ).fetchone()
    if baseline is None or baseline["price"] == 0:
        return None

    return connection.execute(
        """
        SELECT ? AS latest_price,
               ? AS latest_scraped_at,
               ? AS baseline_price,
               ? AS baseline_scraped_at,
               (? - ?) / ? * 100.0 AS percent_change,
               ? AS currency
        """,
        (
            latest["price"],
            latest["scraped_at"],
            baseline["price"],
            baseline["scraped_at"],
            latest["price"],
            baseline["price"],
            baseline["price"],
            latest["currency"],
        ),
    ).fetchone()


def get_all_time_price_range(connection: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    """Return all-time min/max prices and their earliest occurrence dates."""
    row = connection.execute(
        """
        SELECT
            (SELECT price FROM price_history WHERE product_id = ? ORDER BY price ASC, scraped_at ASC LIMIT 1) AS min_price,
            (SELECT scraped_at FROM price_history WHERE product_id = ? ORDER BY price ASC, scraped_at ASC LIMIT 1) AS min_scraped_at,
            (SELECT price FROM price_history WHERE product_id = ? ORDER BY price DESC, scraped_at ASC LIMIT 1) AS max_price,
            (SELECT scraped_at FROM price_history WHERE product_id = ? ORDER BY price DESC, scraped_at ASC LIMIT 1) AS max_scraped_at,
            (SELECT currency FROM price_history WHERE product_id = ? ORDER BY scraped_at DESC LIMIT 1) AS currency
        """,
        (product_id, product_id, product_id, product_id, product_id),
    ).fetchone()
    return row if row is not None and row["min_price"] is not None else None


def get_products_at_or_below_target(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return targeted products whose latest observed price is at/below target."""
    return connection.execute(
        """
        WITH latest_prices AS (
            SELECT product_id, price, currency, scraped_at,
                   ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY scraped_at DESC) AS position
            FROM price_history
        )
        SELECT p.id AS product_id, p.name, p.category, p.retailer, p.url,
               p.target_price, lp.price AS current_price, lp.currency,
               lp.scraped_at AS current_price_at,
               ROUND(p.target_price - lp.price, 2) AS amount_below_target
        FROM products AS p
        JOIN latest_prices AS lp ON lp.product_id = p.id AND lp.position = 1
        WHERE p.target_price IS NOT NULL AND lp.price <= p.target_price
        ORDER BY amount_below_target DESC, p.name
        """
    ).fetchall()
