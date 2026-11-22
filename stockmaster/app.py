from tkinter import ttk

from stockmaster.pages.analytics import AnalyticsPage
from stockmaster.pages.dashboard import DashboardPage
from stockmaster.pages.products import ProductsPage
from stockmaster.pages.sales import SalesPage
from stockmaster.product_store import ProductStore
from stockmaster.sale_store import SaleStore
from stockmaster.styles import configure_styles


class StockMasterApp:
    """Build the main window and manage the active page."""

    def __init__(self, root, product_store=None):
        self.product_store = ProductStore() if product_store is None else product_store
        self.sale_store = SaleStore(self.product_store)
        root.title("StockMaster")
        root.geometry("1200x750")
        root.minsize(740, 480)
        configure_styles(root)

        sidebar = ttk.Frame(root, style="Sidebar.TFrame", padding=(16, 24))
        sidebar.pack(side="left", fill="y")
        ttk.Label(sidebar, text="StockMaster", style="Brand.TLabel").pack(
            anchor="w", padx=12, pady=(0, 28)
        )

        self.navigation_buttons = {}
        for page_class in (DashboardPage, ProductsPage, SalesPage, AnalyticsPage):
            button = ttk.Button(
                sidebar,
                text=page_class.title,
                width=20,
                style="Navigation.TButton",
                command=lambda page=page_class: self.show_page(page),
            )
            button.pack(fill="x", pady=(0, 6))
            self.navigation_buttons[page_class] = button

        ttk.Button(
            sidebar, text="Exit", style="Navigation.TButton", command=root.destroy
        ).pack(side="bottom", fill="x")

        content = ttk.Frame(root)
        content.pack(side="left", fill="both", expand=True)

        header = ttk.Frame(content, style="Surface.TFrame", padding=(28, 20))
        header.pack(fill="x")
        self.header_title = ttk.Label(header, style="PageTitle.TLabel")
        self.header_title.pack(anchor="w")
        ttk.Label(
            header,
            text="Smart Inventory & Sales Analytics System",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        self.page_container = ttk.Frame(content)
        self.page_container.pack(fill="both", expand=True)
        self.current_page = None
        self.show_dashboard()

    def show_dashboard(self):
        self.show_page(DashboardPage)

    def show_page(self, page_class):
        """Show the page and update its header and sidebar selection."""
        if type(self.current_page) is page_class:
            if page_class in (DashboardPage, AnalyticsPage):
                self.current_page.refresh()
            return

        if self.current_page is not None:
            self.current_page.destroy()

        if page_class in (DashboardPage, SalesPage, AnalyticsPage):
            self.current_page = page_class(self.page_container, self.sale_store)
        elif page_class is ProductsPage:
            self.current_page = page_class(self.page_container, self.product_store)
        else:
            self.current_page = page_class(self.page_container)
        self.current_page.pack(fill="both", expand=True)
        self.header_title.configure(text=page_class.title)
        for destination, button in self.navigation_buttons.items():
            button.state(["selected" if destination is page_class else "!selected"])
