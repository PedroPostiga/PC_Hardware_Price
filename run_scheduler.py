"""Run PCComponentes price scraping on a portable daily ``schedule`` loop.

Install the one additional dependency first:
    python -m pip install schedule

Start the scheduler and also perform its first run immediately:
    python run_scheduler.py --run-now

Leave this process running. It will then run daily at 09:00 local time, unless
``--time`` is supplied with another 24-hour ``HH:MM`` value.
"""

from __future__ import annotations

import argparse
import logging
import random
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import schedule

from db_setup import get_connection
from notify import report_target_hits
from scraper import (
    MAX_PRODUCTS_PER_RUN,
    MAX_REQUEST_DELAY_SECONDS,
    MIN_REQUEST_DELAY_SECONDS,
    get_products_to_scrape,
    make_session,
    scrape_product,
)


LOGGER = logging.getLogger("price_tracker.scheduler")
LOG_PATH = Path(__file__).with_name("price_tracker.log")
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(log_path: Path = LOG_PATH) -> None:
    """Send scraper and scheduler logs to both the terminal and rotating file."""
    log_path = log_path.resolve()
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)

    # Avoid duplicate lines if this function is called by an imported test or REPL.
    if not any(
        isinstance(handler, RotatingFileHandler) and handler.baseFilename == str(log_path)
        for handler in root_logger.handlers
    ):
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    if not any(isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler) for handler in root_logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)


def run_scrape_job(max_products: int = MAX_PRODUCTS_PER_RUN) -> None:
    """Run one batch without allowing a product or setup failure to stop scheduling."""
    attempted = 0
    succeeded = 0
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    LOGGER.info("Starting scheduled scrape run at %s", started_at)

    try:
        with get_connection() as connection, make_session() as session:
            products = get_products_to_scrape(connection, max_products)
            if not products:
                LOGGER.warning("No matching PCComponentes products found in the products table.")

            for index, product in enumerate(products):
                attempted += 1
                try:
                    if scrape_product(session, connection, product):
                        succeeded += 1
                except Exception:
                    # ``scrape_product`` handles expected request/parse failures itself.
                    # This catches unforeseen programming, database, or library errors.
                    LOGGER.exception(
                        "Unexpected error while scraping product id=%s (%s); continuing",
                        product["id"],
                        product["name"],
                    )

                if index < len(products) - 1:
                    delay = random.uniform(MIN_REQUEST_DELAY_SECONDS, MAX_REQUEST_DELAY_SECONDS)
                    LOGGER.info("Waiting %.1f seconds before the next request", delay)
                    time.sleep(delay)
    except Exception:
        # For example, this covers a database file/connection failure before a
        # product can be processed. The process remains alive for tomorrow's run.
        LOGGER.exception("Scheduled scrape run encountered a setup-level error")
    finally:
        failed = attempted - succeeded
        LOGGER.info(
            "Run summary: timestamp=%s attempted=%s succeeded=%s failed=%s",
            started_at,
            attempted,
            succeeded,
            failed,
        )
        if attempted > 0 and succeeded == 0:
            LOGGER.warning(
                "All products failed in this run (0/%s succeeded). Check PCComponentes page structure and scraper selectors before the next run.",
                attempted,
            )
        # The scrape connection has already been closed when this ``finally``
        # runs. A short-lived read-only connection keeps the notification check
        # after the run summary and lets it run even after scrape setup errors.
        try:
            with get_connection() as connection:
                report_target_hits(connection)
        except Exception:
            # A reporting problem must not terminate the long-running scheduler.
            LOGGER.exception("Target-price notification check failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Schedule daily PCComponentes price scraping.")
    parser.add_argument("--time", default="09:00", help="Daily local run time in HH:MM format (default: 09:00)")
    parser.add_argument("--limit", type=int, default=MAX_PRODUCTS_PER_RUN, help="Maximum products per run (default: 5)")
    parser.add_argument("--run-now", action="store_true", help="Perform a run immediately before waiting for the daily schedule")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    configure_logging()
    try:
        schedule.every().day.at(args.time).do(run_scrape_job, max_products=args.limit)
    except schedule.ScheduleValueError as error:
        parser.error(f"invalid --time value: {error}")

    LOGGER.info("Scheduler started. Daily run time: %s. Log file: %s", args.time, LOG_PATH)
    if args.run_now:
        run_scrape_job(args.limit)

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        LOGGER.info("Scheduler stopped by user.")


if __name__ == "__main__":
    main()
