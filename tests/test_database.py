import unittest
from datetime import date

from cafe_pos.database import CafeDatabase


class CafeDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = CafeDatabase(":memory:")
        self.beans = self.db.add_ingredient("Coffee beans", "g", 1000, 100)
        self.cup = self.db.add_ingredient("Cup", "each", 10, 2)
        self.latte = self.db.add_product("Latte", "65.50")
        self.db.set_recipe(self.latte, self.beans, 18)
        self.db.set_recipe(self.latte, self.cup, 1)

    def tearDown(self):
        self.db.close()

    def test_sale_decrements_recipe_ingredients_and_reports_payment(self):
        self.db.record_sale([(self.latte, 2)], "Cash")

        ingredients = {row["id"]: row for row in self.db.list_ingredients()}
        self.assertEqual(ingredients[self.beans]["stock"], 964)
        self.assertEqual(ingredients[self.cup]["stock"], 8)
        report = self.db.daily_summary(date.today())
        self.assertEqual(report["sale_count"], 1)
        self.assertEqual(report["total_cents"], 13100)
        self.assertEqual(report["payments"]["Cash"], 13100)
        self.assertEqual(report["top_items"][0]["quantity"], 2)

    def test_sale_without_recipe_is_rejected_without_creating_sale(self):
        product = self.db.add_product("Cookie", "20")

        with self.assertRaisesRegex(ValueError, "recipe"):
            self.db.record_sale([(product, 1)], "Cash")

        self.assertEqual(self.db.daily_summary(date.today())["sale_count"], 0)

    def test_insufficient_stock_rejects_sale_atomically(self):
        self.db.adjust_stock(self.beans, -990, "Waste")

        with self.assertRaisesRegex(ValueError, "Not enough Coffee beans"):
            self.db.record_sale([(self.latte, 1)], "Card")

        self.assertEqual(self.db.daily_summary(date.today())["sale_count"], 0)
        self.assertEqual(
            next(row["stock"] for row in self.db.list_ingredients() if row["id"] == self.cup),
            10,
        )

    def test_stock_adjustment_cannot_make_inventory_negative(self):
        with self.assertRaisesRegex(ValueError, "not enough stock"):
            self.db.adjust_stock(self.cup, -11, "Waste")

        self.assertEqual(
            next(row["stock"] for row in self.db.list_ingredients() if row["id"] == self.cup),
            10,
        )

    def test_set_stock_levels_updates_multiple_ingredients_and_records_movements(self):
        self.db.set_stock_levels([(self.beans, 900), (self.cup, 8)])

        stock = {row["id"]: row["stock"] for row in self.db.list_ingredients()}
        self.assertEqual(stock[self.beans], 900)
        self.assertEqual(stock[self.cup], 8)
        movements = list(
            self.db.connection.execute(
                """SELECT ingredient_id, quantity_change, reason
                   FROM inventory_movements
                   WHERE ingredient_id IN (?, ?) ORDER BY id DESC LIMIT 2""",
                (self.beans, self.cup),
            )
        )
        self.assertEqual(
            {(row["ingredient_id"], row["quantity_change"], row["reason"]) for row in movements},
            {(self.beans, -100, "Adjustment"), (self.cup, -2, "Adjustment")},
        )

    def test_set_stock_levels_rolls_back_if_any_ingredient_is_invalid(self):
        with self.assertRaisesRegex(ValueError, "Ingredient not found"):
            self.db.set_stock_levels([(self.beans, 500), (999, 1)])

        stock = {row["id"]: row["stock"] for row in self.db.list_ingredients()}
        self.assertEqual(stock[self.beans], 1000)
        self.assertEqual(stock[self.cup], 10)

    def test_set_stock_levels_rejects_negative_stock(self):
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            self.db.set_stock_levels([(self.beans, -1)])

        self.assertEqual(
            next(row["stock"] for row in self.db.list_ingredients() if row["id"] == self.beans),
            1000,
        )

    def test_money_uses_cents_without_float_rounding(self):
        self.assertEqual(CafeDatabase.money_to_cents("12.35"), 1235)

    def test_daily_summary_includes_sales_at_the_end_of_the_day(self):
        self.db.connection.execute(
            """INSERT INTO sales (sold_at, total_cents, payment_method)
               VALUES (?, ?, ?)""",
            (f"{date.today().isoformat()}T23:59:59+03:00", 5000, "Card"),
        )
        self.db.connection.commit()

        report = self.db.daily_summary(date.today())

        self.assertEqual(report["sale_count"], 1)
        self.assertEqual(report["total_cents"], 5000)

    def test_non_finite_recipe_and_stock_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite number"):
            self.db.set_recipe(self.latte, self.beans, float("nan"))
        with self.assertRaisesRegex(ValueError, "finite number"):
            self.db.add_ingredient("Sugar", "g", float("inf"), 0)


if __name__ == "__main__":
    unittest.main()
