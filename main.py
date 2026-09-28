from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from cafe_pos.database import CafeDatabase


def money(cents: int) -> str:
    return f"ETB {cents / 100:,.2f}"


class CafeScreen(Screen):
    title = ""

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.layout = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        self.add_widget(self.layout)

    def make_header(self):
        self.layout.clear_widgets()
        nav_scroll = ScrollView(
            size_hint_y=None, height=dp(46), do_scroll_x=True, do_scroll_y=False
        )
        nav = BoxLayout(
            size_hint=(None, None),
            height=dp(46),
            width=dp(552),
            spacing=dp(4),
        )
        for name, label in (
            ("home", "Home"),
            ("pos", "POS"),
            ("menu", "Menu"),
            ("recipes", "Recipes"),
            ("inventory", "Stock"),
            ("reports", "Reports"),
        ):
            nav.add_widget(
                Button(
                    text=label,
                    size_hint_x=None,
                    width=dp(88),
                    on_release=lambda _button, screen=name: self.app.show(screen),
                )
            )
        nav_scroll.add_widget(nav)
        self.layout.add_widget(nav_scroll)
        self.layout.add_widget(
            Label(text=f"[b]{self.title}[/b]", markup=True, size_hint_y=None, height=dp(36))
        )

    def body(self) -> BoxLayout:
        body = BoxLayout(orientation="vertical", spacing=dp(8))
        self.layout.add_widget(body)
        return body

    @staticmethod
    def scroll(content) -> ScrollView:
        view = ScrollView()
        view.add_widget(content)
        return view

    def message(self, text: str, title: str = "Cafe POS") -> None:
        Popup(
            title=title,
            content=Label(text=text, halign="center", valign="middle"),
            size_hint=(0.9, 0.35),
        ).open()

    def text_field(self, hint: str, input_filter=None) -> TextInput:
        return TextInput(
            hint_text=hint,
            multiline=False,
            size_hint_y=None,
            height=dp(44),
            input_filter=input_filter,
        )

    def form_popup(self, title, fields, submit_label, on_submit):
        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        widgets = {}
        for key, hint, field_type, options in fields:
            if field_type == "spinner":
                widget = Spinner(
                    text=options[0] if options else "",
                    values=options,
                    size_hint_y=None,
                    height=dp(44),
                )
            else:
                widget = self.text_field(hint, input_filter=field_type)
            widgets[key] = widget
            content.add_widget(widget)
        popup = Popup(title=title, content=content, size_hint=(0.9, 0.7), auto_dismiss=True)

        def submit(_button):
            try:
                on_submit(widgets)
            except (ValueError, KeyError, sqlite3.IntegrityError) as error:
                self.message(str(error), "Check your entry")
                return
            popup.dismiss()
            self.refresh()

        content.add_widget(
            Button(text=submit_label, size_hint_y=None, height=dp(48), on_release=submit)
        )
        popup.open()

    def refresh(self):
        raise NotImplementedError


class HomeScreen(CafeScreen):
    title = "Cafe overview"

    def refresh(self):
        self.make_header()
        body = self.body()
        summary = self.app.db.daily_summary()
        body.add_widget(Label(text=f"Today: {summary['date']}", size_hint_y=None, height=dp(36)))
        body.add_widget(
            Label(
                text=f"{summary['sale_count']} sales   |   {money(summary['total_cents'])}",
                font_size="22sp",
                size_hint_y=None,
                height=dp(54),
            )
        )
        for method in ("Cash", "Card", "Other"):
            body.add_widget(
                Label(
                    text=f"{method}: {money(summary['payments'].get(method, 0))}",
                    size_hint_y=None,
                    height=dp(32),
                )
            )
        stock = self.app.db.list_ingredients()
        low = [row for row in stock if row["is_low"]]
        body.add_widget(
            Label(
                text=f"Low stock: {len(low)}",
                size_hint_y=None,
                height=dp(38),
            )
        )
        for ingredient in low[:5]:
            body.add_widget(
                Label(
                    text=f"{ingredient['name']}: {ingredient['stock']:g} {ingredient['unit']} left",
                    size_hint_y=None,
                    height=dp(30),
                )
            )
        if not self.app.db.list_products():
            body.add_widget(
                Label(
                    text="Start by adding ingredients, menu items, and recipes.",
                    size_hint_y=None,
                    height=dp(70),
                )
            )


class PosScreen(CafeScreen):
    title = "Point of sale"

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.cart: dict[int, int] = {}

    def refresh(self):
        self.make_header()
        body = self.body()
        products = self.app.db.list_products()
        items = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(5))
        items.bind(minimum_height=items.setter("height"))
        for product in products:
            items.add_widget(
                Button(
                    text=f"{product['name']}  -  {money(product['price_cents'])}",
                    size_hint_y=None,
                    height=dp(50),
                    on_release=lambda _button, p=product: self.add_to_cart(p["id"]),
                )
            )
        body.add_widget(Label(text="Tap a menu item to add it", size_hint_y=None, height=dp(28)))
        body.add_widget(self.scroll(items))
        cart_label = Label(text=self.cart_text(), size_hint_y=None, height=dp(84))
        body.add_widget(cart_label)
        actions = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        actions.add_widget(
            Button(text="Clear", on_release=lambda _button: self.clear_cart())
        )
        actions.add_widget(
            Button(text="Checkout", on_release=lambda _button: self.checkout())
        )
        body.add_widget(actions)

    def cart_text(self):
        lines = []
        total = 0
        products = {p["id"]: p for p in self.app.db.list_products()}
        for product_id, quantity in self.cart.items():
            product = products.get(product_id)
            if product:
                subtotal = product["price_cents"] * quantity
                total += subtotal
                lines.append(f"{quantity} x {product['name']}  {money(subtotal)}")
        if not lines:
            return "Cart is empty"
        return "\n".join(lines) + f"\nTotal: {money(total)}"

    def add_to_cart(self, product_id):
        self.cart[product_id] = self.cart.get(product_id, 0) + 1
        self.refresh()

    def clear_cart(self):
        self.cart.clear()
        self.refresh()

    def checkout(self):
        if not self.cart:
            self.message("Add items to the cart first.")
            return
        methods = Spinner(
            text="Cash", values=("Cash", "Card", "Other"), size_hint_y=None, height=dp(44)
        )
        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        content.add_widget(Label(text=self.cart_text()))
        content.add_widget(methods)
        popup = Popup(title="Complete sale", content=content, size_hint=(0.9, 0.5))

        def complete(_button):
            try:
                self.app.db.record_sale(list(self.cart.items()), methods.text)
            except ValueError as error:
                self.message(str(error), "Sale not completed")
                return
            self.cart.clear()
            popup.dismiss()
            self.app.show("home")

        content.add_widget(
            Button(text="Record sale", size_hint_y=None, height=dp(48), on_release=complete)
        )
        popup.open()


class MenuScreen(CafeScreen):
    title = "Menu items"

    def refresh(self):
        self.make_header()
        body = self.body()
        body.add_widget(
            Button(
                text="Add menu item",
                size_hint_y=None,
                height=dp(48),
                on_release=lambda _button: self.add_product(),
            )
        )
        items = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        items.bind(minimum_height=items.setter("height"))
        for product in self.app.db.list_products():
            items.add_widget(
                Label(
                    text=f"{product['name']}  -  {money(product['price_cents'])}",
                    size_hint_y=None,
                    height=dp(38),
                )
            )
        body.add_widget(self.scroll(items))

    def add_product(self):
        self.form_popup(
            "Add menu item",
            [("name", "Item name", None, None), ("price", "Price in ETB", "float", None)],
            "Save item",
            lambda fields: self.app.db.add_product(
                fields["name"].text, fields["price"].text
            ),
        )


class RecipesScreen(CafeScreen):
    title = "Recipes"

    def refresh(self):
        self.make_header()
        body = self.body()
        body.add_widget(
            Button(
                text="Add or update recipe ingredient",
                size_hint_y=None,
                height=dp(48),
                on_release=lambda _button: self.add_recipe(),
            )
        )
        entries = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        entries.bind(minimum_height=entries.setter("height"))
        for recipe in self.app.db.list_recipes():
            entries.add_widget(
                Label(
                    text=f"{recipe['product_name']}: {recipe['quantity']:g} "
                    f"{recipe['unit']} {recipe['ingredient_name']}",
                    size_hint_y=None,
                    height=dp(38),
                )
            )
        body.add_widget(self.scroll(entries))
        body.add_widget(
            Label(
                text="Use g, ml, or each as the ingredient's stock unit.",
                size_hint_y=None,
                height=dp(40),
            )
        )

    def add_recipe(self):
        products = self.app.db.list_products()
        ingredients = self.app.db.list_ingredients()
        if not products or not ingredients:
            self.message("Add at least one menu item and one ingredient first.")
            return
        product_names = [row["name"] for row in products]
        ingredient_names = [row["name"] for row in ingredients]
        product_by_name = {row["name"]: row["id"] for row in products}
        ingredient_by_name = {row["name"]: row["id"] for row in ingredients}

        def save(fields):
            product_id = product_by_name.get(fields["product"].text)
            ingredient_id = ingredient_by_name.get(fields["ingredient"].text)
            if product_id is None or ingredient_id is None:
                raise ValueError("Choose a menu item and an ingredient.")
            self.app.db.set_recipe(
                product_id, ingredient_id, fields["quantity"].text
            )

        self.form_popup(
            "Recipe ingredient",
            [
                ("product", "", "spinner", product_names),
                ("ingredient", "", "spinner", ingredient_names),
                ("quantity", "Quantity per item", "float", None),
            ],
            "Save recipe",
            save,
        )


class InventoryScreen(CafeScreen):
    title = "Ingredient stock"

    def refresh(self):
        self.make_header()
        body = self.body()
        actions = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        actions.add_widget(Button(text="Add ingredient", on_release=lambda _button: self.add_ingredient()))
        actions.add_widget(Button(text="Adjust stock", on_release=lambda _button: self.adjust_stock()))
        body.add_widget(actions)
        entries = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        entries.bind(minimum_height=entries.setter("height"))
        for ingredient in self.app.db.list_ingredients():
            warning = "  LOW" if ingredient["is_low"] else ""
            entries.add_widget(
                Label(
                    text=f"{ingredient['name']}: {ingredient['stock']:g} "
                    f"{ingredient['unit']} (low at {ingredient['low_stock']:g}){warning}",
                    size_hint_y=None,
                    height=dp(40),
                )
            )
        body.add_widget(self.scroll(entries))

    def add_ingredient(self):
        def save(fields):
            self.app.db.add_ingredient(
                fields["name"].text,
                fields["unit"].text,
                fields["stock"].text or 0,
                fields["low"].text or 0,
            )

        self.form_popup(
            "Add ingredient",
            [
                ("name", "Ingredient name", None, None),
                ("unit", "", "spinner", ["g", "ml", "each"]),
                ("stock", "Opening stock", "float", None),
                ("low", "Low-stock alert level", "float", None),
            ],
            "Save ingredient",
            save,
        )

    def adjust_stock(self):
        ingredients = self.app.db.list_ingredients()
        if not ingredients:
            self.message("Add an ingredient first.")
            return
        names = [row["name"] for row in ingredients]
        ids = {row["name"]: row["id"] for row in ingredients}

        def save(fields):
            try:
                change = float(fields["quantity"].text)
            except ValueError as error:
                raise ValueError("Enter a valid stock change.") from error
            if fields["reason"].text == "Waste":
                change = -abs(change)
            elif fields["reason"].text == "Restock":
                change = abs(change)
            ingredient_id = ids.get(fields["ingredient"].text)
            if ingredient_id is None:
                raise ValueError("Choose an ingredient.")
            self.app.db.adjust_stock(ingredient_id, change, fields["reason"].text)

        self.form_popup(
            "Adjust stock",
            [
                ("ingredient", "", "spinner", names),
                ("reason", "", "spinner", ["Restock", "Waste", "Adjustment"]),
                ("quantity", "Quantity (Adjustment may be + or -)", "float", None),
            ],
            "Save stock change",
            save,
        )


class ReportsScreen(CafeScreen):
    title = "Daily sales report"

    def refresh(self):
        self.make_header()
        body = self.body()
        report = self.app.db.daily_summary(date.today())
        body.add_widget(Label(text=report["date"], size_hint_y=None, height=dp(34)))
        body.add_widget(
            Label(
                text=f"Sales: {report['sale_count']}   |   Total: {money(report['total_cents'])}",
                font_size="20sp",
                size_hint_y=None,
                height=dp(50),
            )
        )
        for method in ("Cash", "Card", "Other"):
            body.add_widget(
                Label(
                    text=f"{method}: {money(report['payments'].get(method, 0))}",
                    size_hint_y=None,
                    height=dp(34),
                )
            )
        body.add_widget(Label(text="Items sold", size_hint_y=None, height=dp(40)))
        entries = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        entries.bind(minimum_height=entries.setter("height"))
        for item in report["top_items"]:
            entries.add_widget(
                Label(
                    text=f"{item['name']}: {item['quantity']}  -  {money(item['total_cents'])}",
                    size_hint_y=None,
                    height=dp(38),
                )
            )
        body.add_widget(self.scroll(entries))


class CafePosApp(App):
    title = "Cafe POS"

    def build(self):
        data_path = Path(self.user_data_dir) / "cafe_pos.sqlite3"
        self.db = CafeDatabase(data_path)
        manager = ScreenManager()
        for name, screen_type in (
            ("home", HomeScreen),
            ("pos", PosScreen),
            ("menu", MenuScreen),
            ("recipes", RecipesScreen),
            ("inventory", InventoryScreen),
            ("reports", ReportsScreen),
        ):
            manager.add_widget(screen_type(self, name=name))
        self.manager = manager
        self.show("home")
        return manager

    def show(self, screen_name):
        self.manager.current = screen_name
        self.manager.current_screen.refresh()

    def on_stop(self):
        if hasattr(self, "db"):
            self.db.close()


if __name__ == "__main__":
    CafePosApp().run()
