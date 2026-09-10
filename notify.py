"""Console and log reporting for target-price hits.

Run ``python notify.py`` to check targets on demand. The scheduler calls the
same reporting function after each scrape batch.
"""

from __future__ import annotations

import logging
import sqlite3

from db_setup import get_connection
from queries import get_products_at_or_below_target


LOGGER = logging.getLogger("price_tracker.notify")


def report_target_hits(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Log every latest price at or below its target and return those rows.

    The project logging configuration sends this logger to both the console and
    ``price_tracker.log``. Empty results are normal for a daily check, so they
    are logged at debug level rather than adding routine noise to the log file.
    """
    target_hits = get_products_at_or_below_target(connection)
    if not target_hits:
        LOGGER.debug("Target-price check completed: no hits.")
        return target_hits

    for hit in target_hits:
        LOGGER.info(
            "Target price hit: %s | current: €%.2f | target: €%.2f | "
            "€%.2f below target | URL: %s",
            hit["name"],
            hit["current_price"],
            hit["target_price"],
            hit["amount_below_target"],
            hit["url"],
        )
    return target_hits


def main() -> None:
    """Configure the existing project handlers and report current target hits."""
    # Imported here to avoid a module-level import cycle: the scheduler imports
    # ``report_target_hits`` to use it after every scrape run.
    from run_scheduler import configure_logging

    configure_logging()
    with get_connection() as connection:
        report_target_hits(connection)


if __name__ == "__main__":
    main()
