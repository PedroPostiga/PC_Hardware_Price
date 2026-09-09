"""Create and configure the SQLite database for the PC Hardware Price Tracker.

Run with:
    python db_setup.py

The database file is created alongside this script as ``price_tracker.db``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


DATABASE_PATH = Path(__file__).with_name("price_tracker.db")


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    retailer TEXT NOT NULL,
    url TEXT NOT NULL,
    target_price REAL CHECK (target_price IS NULL OR target_price >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (retailer, url)
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL,
    price REAL NOT NULL CHECK (price >= 0),
    currency TEXT NOT NULL DEFAULT 'EUR' CHECK (length(currency) = 3),
    scraped_at TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE (product_id, scraped_at)
);

CREATE TABLE IF NOT EXISTS builds (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    budget REAL NOT NULL CHECK (budget >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS build_components (
    build_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    PRIMARY KEY (build_id, product_id),
    FOREIGN KEY (build_id) REFERENCES builds(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_price_history_product_scraped_at
    ON price_history(product_id, scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_build_components_product
    ON build_components(product_id);
"""


def get_connection(database_path: Path = DATABASE_PATH) -> sqlite3.Connection:
    """Return a connection with SQLite foreign-key enforcement enabled."""
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(database_path: Path = DATABASE_PATH) -> None:
    """Create all tables and indexes; safe to call repeatedly."""
    with get_connection(database_path) as connection:
        connection.executescript(SCHEMA_SQL)


if __name__ == "__main__":
    initialize_database()
    print(f"Database ready: {DATABASE_PATH}")
