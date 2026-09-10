"""Find and optionally save a budget-maximizing PC build configuration.

Examples:
    python configurator.py --budget 1200
    python configurator.py --budget 1200 --save --name "Best Value Build"
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Sequence

from db_setup import get_connection
from queries import get_latest_price


CENT = Decimal("0.01")


@dataclass(frozen=True)
class _Candidate:
    """A priced product option prepared for the integer-cent optimizer."""

    category: str
    product_id: int
    name: str
    price_cents: int
    price: Decimal
    currency: str
    scraped_at: str


def _to_cents(value: Decimal | float | int) -> int:
    """Round a monetary value to cents using the conventional half-up rule."""
    amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    return int(amount * 100)


def _selection_key(selection: Sequence[_Candidate]) -> tuple[tuple[str, int], ...]:
    """Give equal-total builds a stable name-then-ID ordering."""
    return tuple((candidate.name.casefold(), candidate.product_id) for candidate in selection)


def _priced_candidates_by_category(
    connection: sqlite3.Connection,
) -> list[tuple[str, list[_Candidate]]] | None:
    """Return dynamic categories and their latest-priced product choices.

    ``None`` means a complete build is impossible. Categories are intentionally
    not skipped: every category already present in ``products`` is a required
    component of this configurable build.
    """
    categories = [
        row["category"]
        for row in connection.execute("SELECT DISTINCT category FROM products ORDER BY category")
    ]
    if not categories:
        print("Cannot build a configuration: there are no products to choose from.")
        return None

    candidates_by_category: list[tuple[str, list[_Candidate]]] = []
    for category in categories:
        candidates: list[_Candidate] = []
        products = connection.execute(
            "SELECT id, name FROM products WHERE category = ? ORDER BY name, id", (category,)
        ).fetchall()
        for product in products:
            latest_price = get_latest_price(connection, product["id"])
            if latest_price is None:
                continue
            price = Decimal(str(latest_price["price"])).quantize(CENT, rounding=ROUND_HALF_UP)
            candidates.append(
                _Candidate(
                    category=category,
                    product_id=product["id"],
                    name=product["name"],
                    price_cents=_to_cents(price),
                    price=price,
                    currency=latest_price["currency"],
                    scraped_at=latest_price["scraped_at"],
                )
            )
        if not candidates:
            print(
                f"Cannot build a configuration: category {category!r} has no products with a recorded price."
            )
            return None
        candidates_by_category.append((category, candidates))
    return candidates_by_category


def _save_build(
    connection: sqlite3.Connection,
    build_name: str,
    budget: Decimal,
    selection: Sequence[_Candidate],
) -> None:
    """Upsert a saved build and replace its components with this recommendation."""
    connection.execute(
        """
        INSERT INTO builds (name, budget) VALUES (?, ?)
        ON CONFLICT(name) DO UPDATE SET budget = excluded.budget
        """,
        (build_name, float(budget)),
    )
    build_id = connection.execute("SELECT id FROM builds WHERE name = ?", (build_name,)).fetchone()["id"]

    # Re-running the same named recommendation must not retain components from
    # an earlier optimization result.
    connection.execute("DELETE FROM build_components WHERE build_id = ?", (build_id,))
    connection.executemany(
        """
        INSERT INTO build_components (build_id, product_id) VALUES (?, ?)
        ON CONFLICT(build_id, product_id) DO NOTHING
        """,
        [(build_id, candidate.product_id) for candidate in selection],
    )
    print(f"Saved build {build_name!r} with {len(selection)} components.")


def find_best_build(
    connection: sqlite3.Connection,
    budget: Decimal | float | int,
    *,
    save: bool = False,
    build_name: str | None = None,
) -> dict[str, object] | None:
    """Return one current-priced product per category with the highest valid total.

    This is an exact multiple-choice knapsack dynamic program over integer
    cents. Its worst-case time is roughly ``categories * budget_in_cents *
    products_per_category`` and memory is ``O(budget_in_cents)``. That is a
    good fit for a small portfolio and ordinary PC-build budgets, but not for a
    huge catalogue or exceptionally large budgets. Equal totals use the
    lexicographically smallest tuple of product names (then IDs), ordered by
    category, for deterministic results.
    """
    try:
        budget_decimal = Decimal(str(budget)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as error:
        raise ValueError("budget must be a valid non-negative monetary amount") from error
    if not budget_decimal.is_finite() or budget_decimal < 0:
        raise ValueError("budget must be a valid non-negative monetary amount")
    if save and not (build_name and build_name.strip()):
        raise ValueError("build_name is required when save=True")

    candidates_by_category = _priced_candidates_by_category(connection)
    if candidates_by_category is None:
        return None

    budget_cents = _to_cents(budget_decimal)
    # Each state maps an achievable spend to its deterministic best selection.
    states: dict[int, tuple[_Candidate, ...]] = {0: ()}
    for _category, candidates in candidates_by_category:
        next_states: dict[int, tuple[_Candidate, ...]] = {}
        for spent_cents, selection in states.items():
            for candidate in candidates:
                total_cents = spent_cents + candidate.price_cents
                if total_cents > budget_cents:
                    continue
                possible_selection = selection + (candidate,)
                existing_selection = next_states.get(total_cents)
                if existing_selection is None or _selection_key(possible_selection) < _selection_key(
                    existing_selection
                ):
                    next_states[total_cents] = possible_selection
        states = next_states
        if not states:
            print(f"No complete build fits within the €{budget_decimal:.2f} budget.")
            return None

    total_cents = max(states)
    selection = states[total_cents]
    total = Decimal(total_cents) / 100
    components = {
        candidate.category: {
            "product_id": candidate.product_id,
            "name": candidate.name,
            "price": float(candidate.price),
            "currency": candidate.currency,
            "scraped_at": candidate.scraped_at,
        }
        for candidate in selection
    }
    result: dict[str, object] = {
        "budget": float(budget_decimal),
        "total": float(total),
        "headroom": float(budget_decimal - total),
        "components": components,
    }
    if save:
        _save_build(connection, build_name.strip(), budget_decimal, selection)
    return result


def _parse_budget(value: str) -> Decimal:
    """Parse a finite, non-negative CLI budget before opening the database."""
    try:
        budget = Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError("budget must be a number") from error
    if not budget.is_finite() or budget < 0:
        raise argparse.ArgumentTypeError("budget must be a non-negative finite amount")
    return budget


def _print_build(result: dict[str, object]) -> None:
    """Render a successful recommendation in a compact terminal-friendly form."""
    print(f"Best build: €{result['total']:.2f} of €{result['budget']:.2f} budget")
    print(f"Remaining headroom: €{result['headroom']:.2f}")
    print("Components:")
    components = result["components"]
    assert isinstance(components, dict)
    for category, component in components.items():
        assert isinstance(component, dict)
        print(
            f"  {category}: {component['name']} — €{component['price']:.2f} "
            f"(latest: {component['scraped_at']})"
        )


def main() -> None:
    """Parse CLI options, calculate a build, and optionally persist it."""
    parser = argparse.ArgumentParser(description="Find the best PC build within a budget.")
    parser.add_argument("--budget", required=True, type=_parse_budget, help="Maximum build cost in EUR")
    parser.add_argument("--save", action="store_true", help="Save the selected build in the database")
    parser.add_argument("--name", help="Saved build name; required with --save")
    arguments = parser.parse_args()
    if arguments.save and not (arguments.name and arguments.name.strip()):
        parser.error("--name is required when --save is used")

    with get_connection() as connection:
        result = find_best_build(
            connection,
            arguments.budget,
            save=arguments.save,
            build_name=arguments.name,
        )
    if result is not None:
        _print_build(result)


if __name__ == "__main__":
    main()
