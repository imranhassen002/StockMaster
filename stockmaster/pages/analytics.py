import tkinter as tk
from decimal import DecimalException
from tkinter import ttk

from stockmaster.analytics import DATE_RANGES, build_report, load_analytics_data
from stockmaster.excel_service import generate_report
from stockmaster.pages.analytics_charts import ChartCard
from stockmaster.pages.excel_dialogs import save_excel


class AnalyticsPage(ttk.Frame):
    title = "Analytics"

    def __init__(self, parent, store):
        super().__init__(parent)
        self.store = store
        self.datasets = None

        toolbar = ttk.Frame(self, padding=(24, 14))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Sales date range").pack(side="left")
        self.date_range = ttk.Combobox(toolbar, values=list(DATE_RANGES), state="readonly", width=13)
        self.date_range.current(0)
        self.date_range.pack(side="left", padx=8)
        self.date_range.bind("<<ComboboxSelected>>", self.update_sales)
        ttk.Button(toolbar, text="Refresh Analytics", style="Primary.TButton",
                   command=self.refresh).pack(side="left", padx=(4, 0))

        report_actions = ttk.Frame(self, padding=(24, 0, 24, 14))
        report_actions.pack(fill="x")
        ttk.Button(report_actions, text="Generate Excel Report", style="Primary.TButton",
                   command=self.export_report).pack(side="left")
        ttk.Label(report_actions, text="All-time sales and current inventory").pack(
            side="left", padx=(10, 0)
        )

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        background = ttk.Style(self).lookup("TFrame", "background")
        self.viewport = tk.Canvas(body, background=background, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.viewport.yview)
        self.viewport.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.viewport.pack(side="left", fill="both", expand=True)
        self.content = ttk.Frame(self.viewport, padding=(24, 0, 24, 18))
        self.window_id = self.viewport.create_window(0, 0, window=self.content, anchor="nw")
        self.content.bind("<Configure>", self.update_scroll_region)
        self.viewport.bind("<Configure>", self.resize_content)

        self.status = ttk.Label(self.content, text="Sales use the selected range. Inventory shows current stock.")
        self.status.pack(anchor="w", pady=(0, 10))
        self.card_grid = ttk.Frame(self.content)
        self.card_grid.pack(fill="x", pady=(0, 10))
        self.cards = []
        self.values = []
        for label in (
            "Total Revenue", "Total Transactions", "Total Units Sold", "Average Transaction Value",
        ):
            card = ttk.Frame(self.card_grid, style="Card.TFrame", padding=(12, 12))
            ttk.Label(card, text=label, style="CardLabel.TLabel", wraplength=145).pack(anchor="w")
            value = ttk.Label(card, text="-", style="CardValue.TLabel")
            value.pack(anchor="w", pady=(6, 0))
            self.cards.append(card)
            self.values.append(value)

        self.revenue_chart = ChartCard(self.content, "Sales Revenue Over Time")
        self.products_chart = ChartCard(self.content, "Top 5 Best-Selling Products")
        self.inventory_chart = ChartCard(self.content, "Inventory Distribution by Category")
        for chart in (self.revenue_chart, self.products_chart, self.inventory_chart):
            chart.pack(fill="x", pady=(0, 12))

        stats = ttk.Frame(self.content, style="Card.TFrame", padding=16)
        stats.pack(fill="x")
        ttk.Label(stats, text="Units Sold per Transaction", style="CardLabel.TLabel").pack(
            anchor="w", pady=(0, 6)
        )
        self.transaction_stats = ttk.Label(stats, style="CardLabel.TLabel", justify="left")
        self.transaction_stats.pack(anchor="w")

        self.column_count = 0
        self.card_grid.bind("<Configure>", self.resize_cards)
        self.bind_scrolling(self.viewport)
        self.refresh()

    def bind_scrolling(self, widget):
        widget.bind("<MouseWheel>", self.scroll, add="+")
        widget.bind("<Button-4>", self.scroll, add="+")
        widget.bind("<Button-5>", self.scroll, add="+")
        for child in widget.winfo_children():
            self.bind_scrolling(child)

    def scroll(self, event):
        direction = -1 if event.num == 4 or event.delta > 0 else 1
        self.viewport.yview_scroll(direction * 3, "units")
        return "break"

    def update_scroll_region(self, _event):
        self.viewport.configure(scrollregion=self.viewport.bbox("all"))

    def resize_content(self, event):
        self.viewport.itemconfigure(self.window_id, width=event.width)
        self.status.configure(wraplength=max(1, event.width - 48))

    def resize_cards(self, event):
        columns = 4 if event.width >= 760 else 2
        if columns == self.column_count:
            return
        self.column_count = columns
        for column in range(len(self.cards)):
            active = column < columns
            self.card_grid.columnconfigure(
                column, weight=int(active), uniform="analytics_cards" if active else ""
            )
        for index, card in enumerate(self.cards):
            row, column = divmod(index, columns)
            card.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)

    def refresh(self):
        try:
            datasets = load_analytics_data(self.store)
            report = build_report(*datasets, self.date_range.get())
        except (OSError, ValueError, DecimalException) as error:
            self.status.configure(text=f"Unable to refresh analytics: {error}")
            return
        self.datasets = datasets
        self.inventory_chart.draw_inventory(report.inventory_by_category)
        self.render_sales(report)

    def export_report(self):
        save_excel(self, "StockMaster Business Report.xlsx",
                   lambda path: generate_report(path, *self.store.load_dashboard_data()))

    def update_sales(self, _event):
        if self.datasets is None:
            self.refresh()
            return
        try:
            report = build_report(*self.datasets, self.date_range.get())
        except (ValueError, DecimalException) as error:
            self.status.configure(text=f"Unable to apply date range: {error}")
            return
        self.render_sales(report)

    def render_sales(self, report):
        status = "Sales use the selected range. Inventory shows current stock."
        empty_message = "No sales data available."
        if not report.transactions and not self.datasets[0].empty:
            empty_message = "No sales match the selected date range."
        if not report.transactions:
            status = f"{empty_message} Inventory shows current stock."
        self.status.configure(text=status)

        values = (f"{report.revenue:,.2f}", f"{report.transactions:,}", f"{report.units_sold:,}",
                  f"{report.average_transaction_value:,.2f}")
        for label, value in zip(self.values, values):
            label.configure(text=value)
        self.revenue_chart.draw_revenue(report.daily_revenue, empty_message)
        self.products_chart.draw_products(report.top_products, empty_message)
        self.transaction_stats.configure(
            text=f"Average  {report.average_units:,.2f}\n"
                 f"Median    {report.median_units:,.2f}\n"
                 f"Maximum  {report.max_units:,}"
        )
