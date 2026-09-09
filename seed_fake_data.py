"""Insert repeatable fake data for local development and query testing.

Run with:
    python seed_fake_data.py
"""

from __future__ import annotations

from db_setup import get_connection, initialize_database


PRODUCTS = [
    ("NVIDIA GeForce RTX 4070 SUPER 12GB", "GPU", "PC Componentes", "https://example.test/gpu/rtx-4070-super", 580.00),
    ("AMD Radeon RX 7800 XT 16GB", "GPU", "Coolmod", "https://example.test/gpu/rx-7800-xt", 470.00),
    ("NVIDIA GeForce RTX 4060 Ti 16GB", "GPU", "PC Componentes", "https://example.test/gpu/rtx-4060-ti", 400.00),
    ("AMD Ryzen 7 7800X3D", "CPU", "Coolmod", "https://example.test/cpu/ryzen-7-7800x3d", 350.00),
    ("AMD Ryzen 5 7600", "CPU", "PC Componentes", "https://example.test/cpu/ryzen-5-7600", 180.00),
    ("Intel Core i5-14600K", "CPU", "Amazon ES", "https://example.test/cpu/core-i5-14600k", 270.00),
    ("Corsair Vengeance 32GB DDR5-6000", "RAM", "PC Componentes", "https://example.test/ram/corsair-vengeance-32gb", 95.00),
]

# Product name -> (price, ISO-8601 UTC timestamp) observations.
PRICE_HISTORY = {
    "NVIDIA GeForce RTX 4070 SUPER 12GB": [(619.99, "2026-01-05T10:00:00Z"), (599.99, "2026-02-03T10:00:00Z"), (579.99, "2026-03-02T10:00:00Z"), (589.99, "2026-04-01T10:00:00Z")],
    "AMD Radeon RX 7800 XT 16GB": [(529.99, "2026-01-05T10:00:00Z"), (499.99, "2026-02-03T10:00:00Z"), (479.99, "2026-03-02T10:00:00Z"), (459.99, "2026-04-01T10:00:00Z")],
    "NVIDIA GeForce RTX 4060 Ti 16GB": [(469.99, "2026-01-05T10:00:00Z"), (449.99, "2026-02-03T10:00:00Z"), (419.99, "2026-03-02T10:00:00Z"), (429.99, "2026-04-01T10:00:00Z")],
    "AMD Ryzen 7 7800X3D": [(399.99, "2026-01-05T10:00:00Z"), (379.99, "2026-02-03T10:00:00Z"), (359.99, "2026-03-02T10:00:00Z"), (369.99, "2026-04-01T10:00:00Z")],
    "AMD Ryzen 5 7600": [(229.99, "2026-01-05T10:00:00Z"), (209.99, "2026-02-03T10:00:00Z"), (189.99, "2026-03-02T10:00:00Z"), (179.99, "2026-04-01T10:00:00Z")],
    "Intel Core i5-14600K": [(319.99, "2026-01-05T10:00:00Z"), (299.99, "2026-02-03T10:00:00Z"), (279.99, "2026-03-02T10:00:00Z"), (289.99, "2026-04-01T10:00:00Z")],
    "Corsair Vengeance 32GB DDR5-6000": [(119.99, "2026-01-05T10:00:00Z"), (109.99, "2026-02-03T10:00:00Z"), (99.99, "2026-03-02T10:00:00Z"), (94.99, "2026-04-01T10:00:00Z")],
}


def seed_database() -> None:
    """Add sample rows without duplicating products, observations, or the build."""
    initialize_database()
    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO products (name, category, retailer, url, target_price)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(retailer, url) DO UPDATE SET
                name = excluded.name,
                category = excluded.category,
                target_price = excluded.target_price
            """,
            PRODUCTS,
        )

        product_ids = {
            row["name"]: row["id"]
            for row in connection.execute("SELECT id, name FROM products")
        }
        observations = [
            (product_ids[name], price, "EUR", scraped_at)
            for name, entries in PRICE_HISTORY.items()
            for price, scraped_at in entries
        ]
        connection.executemany(
            """
            INSERT INTO price_history (product_id, price, currency, scraped_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(product_id, scraped_at) DO UPDATE SET
                price = excluded.price, currency = excluded.currency
            """,
            observations,
        )

        connection.execute(
            "INSERT INTO builds (name, budget) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET budget = excluded.budget",
            ("Balanced Gaming Build", 1200.00),
        )
        build_id = connection.execute(
            "SELECT id FROM builds WHERE name = ?", ("Balanced Gaming Build",)
        ).fetchone()["id"]
        component_names = [
            "AMD Radeon RX 7800 XT 16GB",
            "AMD Ryzen 5 7600",
            "Corsair Vengeance 32GB DDR5-6000",
        ]
        connection.executemany(
            "INSERT OR IGNORE INTO build_components (build_id, product_id) VALUES (?, ?)",
            [(build_id, product_ids[name]) for name in component_names],
        )


if __name__ == "__main__":
    seed_database()
    print("Fake data inserted. Run `python test_queries.py` to inspect it.")
