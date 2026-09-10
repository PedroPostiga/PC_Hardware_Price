"""Export PC Hardware Price Tracker data to timestamped CSV and JSON files.

Examples:
    python export.py --history --format csv
    python export.py --snapshot --builds --format both
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal, Sequence

from db_setup import get_connection
from queries import get_build_with_current_total, get_latest_price, get_price_history


EXPORTS_DIRECTORY = Path("exports")
ExportFormat = Literal["csv", "json", "both"]

HISTORY_FIELDS = [
    "product_id",
    "product_name",
    "category",
    "retailer",
    "url",
    "price",
    "currency",
    "scraped_at",
]
SNAPSHOT_FIELDS = [
    "product_id",
    "name",
    "category",
    "retailer",
    "url",
    "target_price",
    "current_price",
    "currency",
    "current_price_at",
    "at_or_below_target",
]
BUILD_FIELDS = [
    "build_id",
    "build_name",
    "budget",
    "build_created_at",
    "current_total",
    "category",
    "product_name",
    "current_price",
    "currency",
    "current_price_at",
]


def _timestamped_path(stem: str, extension: str, output_directory: Path) -> Path:
    """Create the export directory and return a unique timestamped output path."""
    output_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return output_directory / f"{stem}_{timestamp}.{extension}"


def _requested_formats(export_format: ExportFormat) -> tuple[Literal["csv", "json"], ...]:
    """Normalize the CLI/API format choice into the files that should be written."""
    if export_format == "both":
        return ("csv", "json")
    return (export_format,)


def _write_csv(
    stem: str,
    rows: Sequence[dict[str, object]],
    fields: Sequence[str],
    output_directory: Path,
) -> Path:
    """Write flat rows with headers, returning the timestamped CSV path."""
    output_path = _timestamped_path(stem, "csv", output_directory)
    with output_path.open("w", newline="", encoding="utf-8") as export_file:
        writer = csv.DictWriter(export_file, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def _write_json(stem: str, data: object, output_directory: Path) -> Path:
    """Write UTF-8 JSON with indentation, returning the timestamped JSON path."""
    output_path = _timestamped_path(stem, "json", output_directory)
    with output_path.open("w", encoding="utf-8") as export_file:
        json.dump(data, export_file, ensure_ascii=False, indent=2)
        export_file.write("\n")
    return output_path


def _write_requested(
    stem: str,
    csv_rows: Sequence[dict[str, object]],
    csv_fields: Sequence[str],
    json_data: object,
    export_format: ExportFormat,
    output_directory: Path,
) -> list[Path]:
    """Write all selected representations and print each created path."""
    paths: list[Path] = []
    for selected_format in _requested_formats(export_format):
        if selected_format == "csv":
            paths.append(_write_csv(stem, csv_rows, csv_fields, output_directory))
        else:
            paths.append(_write_json(stem, json_data, output_directory))
    for path in paths:
        print(f"Exported: {path}")
    return paths


def export_price_history(
    connection: sqlite3.Connection,
    export_format: ExportFormat = "both",
    *,
    output_directory: Path = EXPORTS_DIRECTORY,
) -> list[Path]:
    """Export every history observation with its product details.

    The existing ``get_price_history`` query defines the ordering and observation
    fields. No files are written when there are no observations, because an
    empty history export would provide no useful data beyond an empty header or
    JSON array.
    """
    rows: list[dict[str, object]] = []
    products = connection.execute(
        "SELECT id, name, category, retailer, url FROM products ORDER BY category, name, id"
    ).fetchall()
    for product in products:
        for observation in get_price_history(connection, product["id"]):
            rows.append(
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "category": product["category"],
                    "retailer": product["retailer"],
                    "url": product["url"],
                    "price": observation["price"],
                    "currency": observation["currency"],
                    "scraped_at": observation["scraped_at"],
                }
            )
    if not rows:
        print("No price-history observations found; skipping price-history export.")
        return []
    return _write_requested(
        "price-history", rows, HISTORY_FIELDS, rows, export_format, output_directory
    )


def export_current_snapshot(
    connection: sqlite3.Connection,
    export_format: ExportFormat = "both",
    *,
    output_directory: Path = EXPORTS_DIRECTORY,
) -> list[Path]:
    """Export every product and its latest known price, if any.

    Products without price history remain in this inventory export with null
    JSON values (and blank CSV cells) for current-price fields.
    """
    products = connection.execute(
        """
        SELECT id, name, category, retailer, url, target_price
        FROM products
        ORDER BY category, name, id
        """
    ).fetchall()
    if not products:
        print("No products found; skipping current-snapshot export.")
        return []

    rows: list[dict[str, object]] = []
    for product in products:
        latest_price = get_latest_price(connection, product["id"])
        current_price = latest_price["price"] if latest_price is not None else None
        target_price = product["target_price"]
        is_at_or_below_target = (
            current_price is not None and target_price is not None and current_price <= target_price
        )
        rows.append(
            {
                "product_id": product["id"],
                "name": product["name"],
                "category": product["category"],
                "retailer": product["retailer"],
                "url": product["url"],
                "target_price": target_price,
                "current_price": current_price,
                "currency": latest_price["currency"] if latest_price is not None else None,
                "current_price_at": latest_price["scraped_at"] if latest_price is not None else None,
                "at_or_below_target": is_at_or_below_target,
            }
        )
    return _write_requested("current-snapshot", rows, SNAPSHOT_FIELDS, rows, export_format, output_directory)


def export_saved_builds(
    connection: sqlite3.Connection,
    export_format: ExportFormat = "both",
    *,
    output_directory: Path = EXPORTS_DIRECTORY,
) -> list[Path]:
    """Export every saved build with component latest prices.

    JSON nests components under their build. CSV repeats build metadata for each
    component; a build with no components gets one row with blank component
    fields so that it is not omitted from the export.
    """
    builds = connection.execute(
        "SELECT id, name, budget, created_at FROM builds ORDER BY name, id"
    ).fetchall()
    if not builds:
        print("No saved builds found; skipping saved-builds export.")
        return []

    csv_rows: list[dict[str, object]] = []
    json_builds: list[dict[str, object]] = []
    for build in builds:
        component_rows = get_build_with_current_total(connection, build["name"])
        components = [
            {
                "name": component["name"],
                "category": component["category"],
                "current_price": component["price"],
                "currency": component["currency"],
                "current_price_at": component["scraped_at"],
            }
            for component in component_rows
        ]
        current_total = component_rows[0]["build_current_total"] if component_rows else None
        json_builds.append(
            {
                "id": build["id"],
                "name": build["name"],
                "budget": build["budget"],
                "created_at": build["created_at"],
                "current_total": current_total,
                "components": components,
            }
        )

        base_row = {
            "build_id": build["id"],
            "build_name": build["name"],
            "budget": build["budget"],
            "build_created_at": build["created_at"],
            "current_total": current_total,
        }
        if not components:
            csv_rows.append(
                {
                    **base_row,
                    "category": None,
                    "product_name": None,
                    "current_price": None,
                    "currency": None,
                    "current_price_at": None,
                }
            )
            continue
        for component in components:
            csv_rows.append(
                {
                    **base_row,
                    "category": component["category"],
                    "product_name": component["name"],
                    "current_price": component["current_price"],
                    "currency": component["currency"],
                    "current_price_at": component["current_price_at"],
                }
            )
    return _write_requested("saved-builds", csv_rows, BUILD_FIELDS, json_builds, export_format, output_directory)


def main() -> None:
    """Parse selected export modes and create independent files for each one."""
    parser = argparse.ArgumentParser(description="Export PC Hardware Price Tracker data.")
    parser.add_argument("--history", action="store_true", help="Export all price-history observations")
    parser.add_argument("--snapshot", action="store_true", help="Export the current product inventory")
    parser.add_argument("--builds", action="store_true", help="Export all saved builds")
    parser.add_argument("--format", choices=("csv", "json", "both"), default="both", help="Output format (default: both)")
    arguments = parser.parse_args()
    if not any((arguments.history, arguments.snapshot, arguments.builds)):
        parser.error("select at least one export mode: --history, --snapshot, or --builds")

    with get_connection() as connection:
        if arguments.history:
            export_price_history(connection, arguments.format)
        if arguments.snapshot:
            export_current_snapshot(connection, arguments.format)
        if arguments.builds:
            export_saved_builds(connection, arguments.format)


if __name__ == "__main__":
    main()
