from collections import Counter
from datetime import timedelta
from textwrap import fill
from tkinter import ttk

from matplotlib import dates, ticker
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


BLUE = "#245CC7"
INK = "#18263D"
MUTED = "#52627A"
GRID = "#DCE4EF"
PIE_COLORS = ("#245CC7", "#148276", "#9661BA", "#D48424", "#4D83B2", "#BB5B75")


class ChartCard(ttk.Frame):
    """Keep one embedded figure and reuse its axes on refresh."""

    def __init__(self, parent, title, height=280):
        super().__init__(parent, style="Card.TFrame", padding=12)
        self.title = title
        self.height = height
        self.figure = Figure(figsize=(6, height / 100), dpi=100, layout="constrained")
        self.axes = self.figure.add_subplot()
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill="x", expand=True)

    def prepare(self, height=None):
        self.canvas.get_tk_widget().configure(height=self.height if height is None else height)
        self.axes.clear()
        self.axes.set_aspect("auto")
        self.axes.set_title(self.title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=12)
        self.axes.tick_params(length=0, labelsize=9, colors=MUTED)
        for spine in self.axes.spines.values():
            spine.set_visible(False)
        return self.axes

    def show_empty(self, message):
        ax = self.prepare()
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(0.5, 0.5, message, ha="center", va="center", color=MUTED, transform=ax.transAxes)
        self.canvas.draw_idle()

    def draw_revenue(self, daily_revenue, empty_message):
        if not daily_revenue:
            self.show_empty(empty_message)
            return
        ax = self.prepare()
        days, revenue = zip(*daily_revenue)
        ax.plot(days, [float(amount) for amount in revenue], color=BLUE, linewidth=2,
                marker="o" if len(days) <= 30 else None, markersize=4)
        if len(days) == 1:
            ax.set_xlim(days[0] - timedelta(days=1), days[0] + timedelta(days=1))
            ax.set_xticks(days)
            ax.xaxis.set_major_formatter(dates.DateFormatter("%d %b %Y"))
        else:
            locator = dates.AutoDateLocator(minticks=3, maxticks=6)
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(dates.ConciseDateFormatter(locator))
        ax.set_ylim(bottom=0)
        ax.set_xlabel("Sale date", color=MUTED)
        ax.set_ylabel("Revenue", color=MUTED)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda amount, _: f"{amount:,.2f}"))
        ax.grid(axis="y", color=GRID)
        ax.set_axisbelow(True)
        self.canvas.draw_idle()

    def draw_products(self, products, empty_message):
        if not products:
            self.show_empty(empty_message)
            return
        name_counts = Counter(name.casefold() for _, name, _ in products)
        labels = [
            fill(f"{name} [{product_id}]" if name_counts[name.casefold()] > 1 else name, width=23)
            for product_id, name, _ in products
        ]
        tallest_label = max(label.count("\n") + 1 for label in labels)
        ax = self.prepare(max(self.height, 115 + 15 * len(labels) * tallest_label))
        positions = range(len(products))
        ax.barh(positions, [quantity for _, _, quantity in products], color=BLUE)
        ax.set_yticks(positions, labels)
        ax.invert_yaxis()
        ax.set_xlabel("Units sold", color=MUTED)
        ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=6, integer=True))
        ax.grid(axis="x", color=GRID)
        ax.set_axisbelow(True)
        self.canvas.draw_idle()

    def draw_inventory(self, inventory):
        if not inventory:
            self.show_empty("No inventory with available stock.")
            return
        categories, quantities = zip(*inventory)
        total = sum(quantities)
        shares = [quantity / total for quantity in quantities]
        labels = [fill(f"{category} ({share:.1%})", width=26)
                  for category, share in zip(categories, shares)]
        lines = sum(label.count("\n") + 1 for label in labels)
        ax = self.prepare(max(self.height, 65 + 18 * lines))
        wedges, _ = ax.pie(
            shares, colors=PIE_COLORS, startangle=90,
            wedgeprops={"edgecolor": "white", "linewidth": 1},
        )
        ax.legend(wedges, labels, title="Category share", loc="center left",
                  bbox_to_anchor=(1, 0.5), frameon=False, fontsize=9, labelcolor=INK)
        self.canvas.draw_idle()
