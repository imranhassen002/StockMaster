import csv
from decimal import DecimalException
from tkinter import ttk

from stockmaster.products import inventory_summary
from stockmaster.sales import total_revenue


class DashboardPage(ttk.Frame):
    """Display the inventory and sales summary cards."""

    title = "Dashboard"
    statistics = (
        "Total Products", "Total Inventory Value", "Total Sales Revenue", "Low / Out of Stock Products",
    )

    def __init__(self, parent, store):
        super().__init__(parent, padding=28)
        self.store = store
        ttk.Label(
            self, text="Business Overview", style="SectionTitle.TLabel"
        ).pack(anchor="w", pady=(0, 14))

        self.card_grid = ttk.Frame(self)
        self.card_grid.pack(fill="x")
        self.cards = []
        self.values = []
        for label in self.statistics:
            card = ttk.Frame(self.card_grid, style="Card.TFrame", padding=(16, 18))
            ttk.Label(card, text=label, style="CardLabel.TLabel").pack(anchor="w")
            value = ttk.Label(card, style="CardValue.TLabel")
            value.pack(anchor="w", pady=(8, 0))
            self.values.append(value)
            self.cards.append(card)

        self.error_message = ttk.Label(self)
        self.error_message.pack(anchor="w", pady=(8, 0))
        self.error_message.bind("<Configure>", self.wrap_error)
        self.column_count = 0
        self.card_grid.bind("<Configure>", self.resize_cards)
        self.refresh()

    def refresh(self):
        try:
            products, sales = self.store.load_dashboard_data()
            count, value, low_stock = inventory_summary(products)
            revenue = total_revenue(sales)
        except (OSError, ValueError, csv.Error, DecimalException) as error:
            values = ("—", "—", "—", "—")
            self.error_message.configure(text=f"Unable to load dashboard data: {error}")
        else:
            values = (str(count), f"{value:,.2f}", f"{revenue:,.2f}", str(low_stock))
            self.error_message.configure(text="")

        for label, value in zip(self.values, values):
            label.configure(text=value)

    def wrap_error(self, event):
        self.error_message.configure(wraplength=max(self.card_grid.winfo_width(), 300))

    def resize_cards(self, event):
        """Use two columns when the cards cannot fit comfortably in one row."""
        widest_card = max(card.winfo_reqwidth() for card in self.cards)
        columns = 4 if event.width >= 4 * (widest_card + 16) else 2
        if columns == self.column_count:
            return

        self.column_count = columns
        for column in range(len(self.cards)):
            active = column < columns
            self.card_grid.columnconfigure(
                column, weight=int(active), uniform="cards" if active else ""
            )
        for index, card in enumerate(self.cards):
            row, column = divmod(index, columns)
            card.grid(row=row, column=column, sticky="nsew", padx=6, pady=6)
