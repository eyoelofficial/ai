from __future__ import annotations

import sqlite3
import math
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable


class CafeDatabase:
    """SQLite storage and transactional sales/inventory operations."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS ingredients (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                unit TEXT NOT NULL CHECK (unit IN ('g', 'ml', 'each')),
                stock REAL NOT NULL DEFAULT 0 CHECK (stock >= 0),
                low_stock REAL NOT NULL DEFAULT 0 CHECK (low_stock >= 0)
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS recipes (
                product_id INTEGER NOT NULL REFERENCES products(id),
                ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
                quantity REAL NOT NULL CHECK (quantity > 0),
                PRIMARY KEY (product_id, ingredient_id)
            );
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY,
                sold_at TEXT NOT NULL,
                total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
                payment_method TEXT NOT NULL CHECK (payment_method IN ('Cash', 'Card', 'Other'))
            );
            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY,
                sale_id INTEGER NOT NULL REFERENCES sales(id),
                product_id INTEGER NOT NULL REFERENCES products(id),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
                subtotal_cents INTEGER NOT NULL CHECK (subtotal_cents >= 0)
            );
            CREATE TABLE IF NOT EXISTS inventory_movements (
                id INTEGER PRIMARY KEY,
                ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
                quantity_change REAL NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sales_sold_at ON sales(sold_at);
            CREATE INDEX IF NOT EXISTS idx_sale_items_sale_id ON sale_items(sale_id);
            """
        )
        self.connection.commit()

    @staticmethod
    def money_to_cents(value: str | int | float | Decimal) -> int:
        try:
            amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError) as error:
            raise ValueError("Enter a valid price.") from error
        if not amount.is_finite() or amount < 0:
            raise ValueError("Price must be zero or greater.")
        return int(amount * 100)

    @staticmethod
    def _positive_number(value: str | int | float, label: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Enter a valid {label}.") from error
        if not math.isfinite(number):
            raise ValueError(f"{label.capitalize()} must be a finite number.")
        if number <= 0:
            raise ValueError(f"{label.capitalize()} must be greater than zero.")
        return number

    @staticmethod
    def _nonnegative_number(value: str | int | float, label: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Enter a valid {label}.") from error
        if not math.isfinite(number):
            raise ValueError(f"{label.capitalize()} must be a finite number.")
        if number < 0:
            raise ValueError(f"{label.capitalize()} cannot be negative.")
        return number

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def add_ingredient(
        self, name: str, unit: str, opening_stock: float = 0, low_stock: float = 0
    ) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Ingredient name is required.")
        if unit not in {"g", "ml", "each"}:
            raise ValueError("Unit must be g, ml, or each.")
        opening_stock = self._nonnegative_number(opening_stock, "opening stock")
        low_stock = self._nonnegative_number(low_stock, "low-stock level")
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO ingredients (name, unit, stock, low_stock) VALUES (?, ?, ?, ?)",
                (name, unit, opening_stock, low_stock),
            )
            ingredient_id = cursor.lastrowid
            if opening_stock:
                self.connection.execute(
                    """INSERT INTO inventory_movements
                       (ingredient_id, quantity_change, reason, created_at)
                       VALUES (?, ?, 'Opening stock', ?)""",
                    (ingredient_id, opening_stock, self._now()),
                )
        return int(ingredient_id)

    def add_product(self, name: str, price: str | int | float | Decimal) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Product name is required.")
        price_cents = self.money_to_cents(price)
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO products (name, price_cents) VALUES (?, ?)", (name, price_cents)
            )
        return int(cursor.lastrowid)

    def set_recipe(self, product_id: int, ingredient_id: int, quantity: float) -> None:
        quantity = self._positive_number(quantity, "recipe quantity")
        with self.connection:
            self.connection.execute(
                """INSERT INTO recipes (product_id, ingredient_id, quantity)
                   VALUES (?, ?, ?)
                   ON CONFLICT(product_id, ingredient_id)
                   DO UPDATE SET quantity = excluded.quantity""",
                (product_id, ingredient_id, quantity),
            )

    def adjust_stock(
        self, ingredient_id: int, quantity_change: float, reason: str = "Restock"
    ) -> None:
        if reason not in {"Restock", "Waste", "Adjustment"}:
            raise ValueError("Choose Restock, Waste, or Adjustment.")
        quantity_change = float(quantity_change)
        if not math.isfinite(quantity_change) or quantity_change == 0:
            raise ValueError("Stock change must not be zero.")
        with self.connection:
            row = self.connection.execute(
                "SELECT stock FROM ingredients WHERE id = ?", (ingredient_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Ingredient not found.")
            new_stock = row["stock"] + quantity_change
            if new_stock < -1e-9:
                raise ValueError("There is not enough stock for that change.")
            self.connection.execute(
                "UPDATE ingredients SET stock = ? WHERE id = ?",
                (max(0, new_stock), ingredient_id),
            )
            self.connection.execute(
                """INSERT INTO inventory_movements
                   (ingredient_id, quantity_change, reason, created_at)
                   VALUES (?, ?, ?, ?)""",
                (ingredient_id, quantity_change, reason, self._now()),
            )

    def set_stock_levels(self, stock_levels: Iterable[tuple[int, float]]) -> None:
        """Set multiple on-hand quantities atomically and record their adjustments."""
        normalized: dict[int, float] = {}
        for ingredient_id, stock in stock_levels:
            if ingredient_id in normalized:
                raise ValueError("Each ingredient can only be included once.")
            normalized[ingredient_id] = self._nonnegative_number(stock, "stock level")
        if not normalized:
            raise ValueError("Provide at least one ingredient stock level.")

        with self.connection:
            now = self._now()
            for ingredient_id, stock in normalized.items():
                row = self.connection.execute(
                    "SELECT stock FROM ingredients WHERE id = ?", (ingredient_id,)
                ).fetchone()
                if row is None:
                    raise ValueError("Ingredient not found.")
                change = stock - row["stock"]
                self.connection.execute(
                    "UPDATE ingredients SET stock = ? WHERE id = ?",
                    (stock, ingredient_id),
                )
                if change != 0:
                    self.connection.execute(
                        """INSERT INTO inventory_movements
                           (ingredient_id, quantity_change, reason, created_at)
                           VALUES (?, ?, 'Adjustment', ?)""",
                        (ingredient_id, change, now),
                    )

    def record_sale(self, items: Iterable[tuple[int, int]], payment_method: str) -> int:
        if payment_method not in {"Cash", "Card", "Other"}:
            raise ValueError("Choose Cash, Card, or Other as the payment method.")
        quantities: dict[int, int] = {}
        for product_id, quantity in items:
            if not isinstance(quantity, int) or quantity <= 0:
                raise ValueError("Sale quantities must be positive whole numbers.")
            quantities[product_id] = quantities.get(product_id, 0) + quantity
        if not quantities:
            raise ValueError("Add at least one item before checkout.")

        with self.connection:
            products: dict[int, sqlite3.Row] = {}
            for product_id in quantities:
                product = self.connection.execute(
                    "SELECT id, name, price_cents FROM products WHERE id = ? AND active = 1",
                    (product_id,),
                ).fetchone()
                if product is None:
                    raise ValueError("A selected product is unavailable.")
                products[product_id] = product
                has_recipe = self.connection.execute(
                    "SELECT 1 FROM recipes WHERE product_id = ? LIMIT 1", (product_id,)
                ).fetchone()
                if has_recipe is None:
                    raise ValueError(f"Add a recipe for {product['name']} before selling it.")

            required: dict[int, float] = {}
            for product_id, quantity in quantities.items():
                for recipe in self.connection.execute(
                    "SELECT ingredient_id, quantity FROM recipes WHERE product_id = ?",
                    (product_id,),
                ):
                    ingredient_id = recipe["ingredient_id"]
                    required[ingredient_id] = (
                        required.get(ingredient_id, 0) + recipe["quantity"] * quantity
                    )
            for ingredient_id, needed in required.items():
                stock = self.connection.execute(
                    "SELECT name, stock, unit FROM ingredients WHERE id = ?", (ingredient_id,)
                ).fetchone()
                if stock is None or stock["stock"] + 1e-9 < needed:
                    name = stock["name"] if stock else "Ingredient"
                    unit = stock["unit"] if stock else ""
                    available = stock["stock"] if stock else 0
                    raise ValueError(
                        f"Not enough {name}: need {needed:g} {unit}, have {available:g} {unit}."
                    )

            total_cents = sum(
                products[product_id]["price_cents"] * quantity
                for product_id, quantity in quantities.items()
            )
            cursor = self.connection.execute(
                "INSERT INTO sales (sold_at, total_cents, payment_method) VALUES (?, ?, ?)",
                (self._now(), total_cents, payment_method),
            )
            sale_id = int(cursor.lastrowid)
            for product_id, quantity in quantities.items():
                price = products[product_id]["price_cents"]
                self.connection.execute(
                    """INSERT INTO sale_items
                       (sale_id, product_id, quantity, unit_price_cents, subtotal_cents)
                       VALUES (?, ?, ?, ?, ?)""",
                    (sale_id, product_id, quantity, price, price * quantity),
                )
            for ingredient_id, needed in required.items():
                self.connection.execute(
                    "UPDATE ingredients SET stock = stock - ? WHERE id = ?",
                    (needed, ingredient_id),
                )
                self.connection.execute(
                    """INSERT INTO inventory_movements
                       (ingredient_id, quantity_change, reason, created_at)
                       VALUES (?, ?, 'Sale', ?)""",
                    (ingredient_id, -needed, self._now()),
                )
        return sale_id

    def list_products(self, active_only: bool = True) -> list[sqlite3.Row]:
        query = "SELECT id, name, price_cents FROM products"
        if active_only:
            query += " WHERE active = 1"
        return list(self.connection.execute(query + " ORDER BY name"))

    def list_ingredients(self) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                """SELECT id, name, unit, stock, low_stock,
                          CASE WHEN stock <= low_stock THEN 1 ELSE 0 END AS is_low
                   FROM ingredients ORDER BY name"""
            )
        )

    def list_recipes(self) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                """SELECT r.product_id, r.ingredient_id, p.name AS product_name,
                          i.name AS ingredient_name, i.unit, r.quantity
                   FROM recipes r
                   JOIN products p ON p.id = r.product_id
                   JOIN ingredients i ON i.id = r.ingredient_id
                   ORDER BY p.name, i.name"""
            )
        )

    def daily_summary(self, report_date: date | str | None = None) -> dict:
        if report_date is None:
            report_date = date.today()
        date_text = report_date.isoformat() if isinstance(report_date, date) else report_date
        start = f"{date_text}T00:00:00"
        end = f"{(date.fromisoformat(date_text) + timedelta(days=1)).isoformat()}T00:00:00"
        totals = self.connection.execute(
            """SELECT COUNT(*) AS sale_count, COALESCE(SUM(total_cents), 0) AS total_cents
               FROM sales WHERE sold_at >= ? AND sold_at < ?""",
            (start, end),
        ).fetchone()
        payments = {
            row["payment_method"]: row["amount"]
            for row in self.connection.execute(
                """SELECT payment_method, COALESCE(SUM(total_cents), 0) AS amount
                   FROM sales WHERE sold_at >= ? AND sold_at < ?
                   GROUP BY payment_method""",
                (start, end),
            )
        }
        top_items = list(
            self.connection.execute(
                """SELECT p.name, SUM(si.quantity) AS quantity,
                          SUM(si.subtotal_cents) AS total_cents
                   FROM sale_items si
                   JOIN sales s ON s.id = si.sale_id
                   JOIN products p ON p.id = si.product_id
                   WHERE s.sold_at >= ? AND s.sold_at < ?
                   GROUP BY p.id ORDER BY quantity DESC, p.name""",
                (start, end),
            )
        )
        return {
            "date": date_text,
            "sale_count": totals["sale_count"],
            "total_cents": totals["total_cents"],
            "payments": payments,
            "top_items": top_items,
        }

    def sales_history(self, limit: int = 50) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                """SELECT id, sold_at, total_cents, payment_method
                   FROM sales ORDER BY sold_at DESC, id DESC LIMIT ?""",
                (limit,),
            )
        )
