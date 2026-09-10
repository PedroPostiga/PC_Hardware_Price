"""Matplotlib charts for the PC Hardware Price Tracker.

Examples:
    python visualize.py --product "AMD Radeon RX 7800 XT 16GB"
    python visualize.py --compare "GPU A" "GPU B" --show
    python visualize.py --category GPU --no-save --show

Chart functions deliberately accept a SQLite connection.  This keeps charting
read-only and lets callers decide when the database connection is closed.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Sequence

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from db_setup import get_connection
from queries import get_price_history, get_product_id


CHARTS_DIRECTORY = Path("charts")


def _parse_scraped_at(value: str) -> datetime:
    """Convert either supported UTC ISO-8601 timestamp precision to datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _slugify(value: str) -> str:
    """Return a portable, readable filename stem."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "chart"


def _timestamped_path(stem: str, charts_directory: Path) -> Path:
    """Create the output directory and return a collision-resistant PNG path."""
    charts_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return charts_directory / f"{_slugify(stem)}_{timestamp}.png"


def _format_axis(axis: Axes, title: str) -> None:
    """Apply consistent date, currency, and title formatting to a chart axis."""
    axis.set_title(title)
    axis.set_xlabel("Scraped at")
    axis.set_ylabel("Price (€)")
    axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(axis.xaxis.get_major_locator()))
    axis.grid(True, alpha=0.25)


def _draw_history(axis: Axes, history: Sequence[sqlite3.Row], label: str | None = None) -> None:
    """Draw a history, using a marker and note when it has only one observation."""
    dates = [_parse_scraped_at(row["scraped_at"]) for row in history]
    prices = [row["price"] for row in history]
    if len(history) == 1:
        axis.plot(dates, prices, marker="o", linestyle="None", label=label)
        axis.annotate(
            "One observation",
            xy=(dates[0], prices[0]),
            xytext=(6, 8),
            textcoords="offset points",
            fontsize=8,
        )
    else:
        axis.plot(dates, prices, marker="o", markersize=3, label=label)


def _finish_chart(
    figure: Figure,
    *,
    stem: str,
    save: bool,
    show: bool,
    charts_directory: Path,
) -> Path | None:
    """Save and/or display a completed chart, then release its figure resources."""
    output_path: Path | None = None
    figure.tight_layout()
    if save:
        output_path = _timestamped_path(stem, charts_directory)
        figure.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"Saved chart: {output_path}")
    if show:
        plt.show()
    plt.close(figure)
    return output_path


def plot_product_price_history(
    connection: sqlite3.Connection,
    product_name: str,
    *,
    save: bool = True,
    show: bool = False,
    charts_directory: Path = CHARTS_DIRECTORY,
) -> Path | None:
    """Plot one product's history, returning its saved path or ``None``.

    A product without observations produces a clear message and no empty chart.
    A single observation is shown as a marker because it is not a trend.
    """
    try:
        product_id = get_product_id(connection, product_name)
    except ValueError:
        print(f"No product found named: {product_name}. Skipping chart.")
        return None
    history = get_price_history(connection, product_id)
    if not history:
        print(f"No price history for product: {product_name}. Skipping chart.")
        return None

    figure, axis = plt.subplots(figsize=(10, 5))
    _draw_history(axis, history)
    _format_axis(axis, f"Price history: {product_name}")
    figure.autofmt_xdate()
    return _finish_chart(
        figure,
        stem=product_name,
        save=save,
        show=show,
        charts_directory=charts_directory,
    )


def plot_product_comparison(
    connection: sqlite3.Connection,
    product_names: Sequence[str],
    *,
    save: bool = True,
    show: bool = False,
    charts_directory: Path = CHARTS_DIRECTORY,
) -> Path | None:
    """Overlay named products with history, skipping products with no observations."""
    if not product_names:
        raise ValueError("At least one product name is required for a comparison.")

    histories: list[tuple[str, list[sqlite3.Row]]] = []
    for product_name in dict.fromkeys(product_names):
        try:
            product_id = get_product_id(connection, product_name)
        except ValueError:
            print(f"No product found named: {product_name}. Skipping series.")
            continue
        history = get_price_history(connection, product_id)
        if not history:
            print(f"No price history for product: {product_name}. Skipping series.")
            continue
        histories.append((product_name, history))

    if not histories:
        print("None of the requested products have price history. Skipping chart.")
        return None

    figure, axis = plt.subplots(figsize=(11, 5.5))
    for product_name, history in histories:
        _draw_history(axis, history, label=product_name)
    _format_axis(axis, "Product price comparison")
    if len(histories) > 1:
        axis.legend()
    figure.autofmt_xdate()
    return _finish_chart(
        figure,
        # Keep comparison output paths short even when product names are long.
        stem="product-comparison",
        save=save,
        show=show,
        charts_directory=charts_directory,
    )


def plot_category_price_histories(
    connection: sqlite3.Connection,
    category: str,
    *,
    save: bool = True,
    show: bool = False,
    charts_directory: Path = CHARTS_DIRECTORY,
) -> Path | None:
    """Plot one small-multiple panel per product in a category.

    Panels omit products with no history rather than showing unexplained blank
    axes.  A shared y-axis makes relative prices directly comparable.
    """
    products = connection.execute(
        "SELECT id, name FROM products WHERE category = ? ORDER BY name", (category,)
    ).fetchall()
    if not products:
        print(f"No products found in category: {category}. Skipping chart.")
        return None

    histories: list[tuple[str, list[sqlite3.Row]]] = []
    for product in products:
        history = get_price_history(connection, product["id"])
        if not history:
            print(f"No price history for product: {product['name']}. Omitting panel.")
            continue
        histories.append((product["name"], history))
    if not histories:
        print(f"No products in category {category} have price history. Skipping chart.")
        return None

    columns = min(3, len(histories))
    rows = (len(histories) + columns - 1) // columns
    figure, axes = plt.subplots(rows, columns, figsize=(5 * columns, 3.7 * rows), sharey=True, squeeze=False)
    prices = [row["price"] for _, history in histories for row in history]
    minimum, maximum = min(prices), max(prices)
    padding = max((maximum - minimum) * 0.08, maximum * 0.02, 1.0)

    for axis, (product_name, history) in zip(axes.flat, histories):
        _draw_history(axis, history)
        _format_axis(axis, product_name)
        axis.set_ylim(minimum - padding, maximum + padding)
    for axis in axes.flat[len(histories):]:
        figure.delaxes(axis)

    figure.suptitle(f"{category} price histories", fontsize=14)
    figure.autofmt_xdate()
    return _finish_chart(
        figure,
        stem=f"{category}-price-histories",
        save=save,
        show=show,
        charts_directory=charts_directory,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the three chart modes."""
    parser = argparse.ArgumentParser(description="Create PC hardware price-history charts.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--product", metavar="NAME", help="Plot one product.")
    mode.add_argument("--compare", metavar="NAME", nargs="+", help="Overlay named products.")
    mode.add_argument("--category", metavar="CATEGORY", help="Create category small multiples.")
    parser.add_argument("--show", action="store_true", help="Also display the chart interactively.")
    parser.add_argument("--no-save", action="store_true", help="Do not save a PNG (use with --show for display-only).")
    return parser


def main() -> None:
    """Parse CLI arguments and run the selected chart operation."""
    arguments = _build_parser().parse_args()
    save = not arguments.no_save
    with get_connection() as connection:
        if arguments.product:
            plot_product_price_history(connection, arguments.product, save=save, show=arguments.show)
        elif arguments.compare:
            plot_product_comparison(connection, arguments.compare, save=save, show=arguments.show)
        else:
            plot_category_price_histories(connection, arguments.category, save=save, show=arguments.show)


if __name__ == "__main__":
    main()
