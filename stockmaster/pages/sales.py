import csv
import tkinter as tk
from datetime import date
from decimal import DecimalException
from tkinter import messagebox, ttk

from stockmaster.excel_service import export_sales
from stockmaster.pages.excel_dialogs import save_excel
from stockmaster.sales import filter_sales, parse_sale_quantity, total_revenue


STORAGE_ERRORS = (OSError, ValueError, csv.Error, DecimalException)


class SalesPage(ttk.Frame):
    title = "Sales"
    columns = (
        ("Sale ID", 115, "w"), ("Date and Time", 160, "w"),
        ("Product ID", 115, "w"), ("Product Name", 155, "w"),
        ("Quantity Sold", 108, "e"), ("Unit Price", 90, "e"),
        ("Total Amount", 110, "e"),
    )

    def __init__(self, parent, store):
        super().__init__(parent, padding=28)
        self.store = store
        self.sales = []
        self.sale_date = None
        self.search_text = tk.StringVar(self)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(0, 12))
        ttk.Button(
            actions, text="Record New Sale", style="Primary.TButton", command=self.record_sale,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Export Sales", style="Primary.TButton",
                   command=self.export_excel).pack(side="left")

        summary = ttk.Frame(self, style="Card.TFrame", padding=(12, 8))
        summary.pack(fill="x", pady=(0, 12))
        self.revenue_label = ttk.Label(summary, style="CardLabel.TLabel")
        self.revenue_label.pack(side="left", padx=(0, 18))
        self.transactions_label = ttk.Label(summary, style="CardLabel.TLabel")
        self.transactions_label.pack(side="left")

        search = ttk.Frame(self)
        search.pack(fill="x", pady=(0, 8))
        ttk.Label(search, text="Search by product name, product ID, or sale ID").pack(anchor="w")
        ttk.Entry(search, textvariable=self.search_text).pack(fill="x", pady=(3, 0))

        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(0, 12))
        ttk.Label(filters, text="Date (YYYY-MM-DD)").pack(side="left")
        self.date_entry = ttk.Entry(filters, width=12)
        self.date_entry.pack(side="left", padx=8)
        self.date_entry.bind("<Return>", lambda event: self.apply_date_filter())
        ttk.Button(filters, text="Apply", command=self.apply_date_filter).pack(side="left")
        ttk.Button(filters, text="Clear", command=self.clear_date_filter).pack(side="left", padx=8)

        ttk.Label(self, text="Sales History", style="SectionTitle.TLabel").pack(
            anchor="w", pady=(0, 6)
        )
        table_frame = ttk.Frame(self, style="Surface.TFrame")
        table_frame.pack(fill="both", expand=True)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(
            table_frame, show="headings", selectmode="browse",
            columns=[heading for heading, _, _ in self.columns],
        )
        for heading, width, anchor in self.columns:
            self.table.heading(heading, text=heading, anchor=anchor)
            self.table.column(heading, width=width, minwidth=width, anchor=anchor)
        self.table.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        # Same light stripes as the Products table for consistent styling.
        self.table.tag_configure("Stripe", background="#F5F8FC")

        self.search_trace = self.search_text.trace_add("write", self.display_sales)
        self.refresh()

    def destroy(self):
        self.search_text.trace_remove("write", self.search_trace)
        super().destroy()

    def refresh(self):
        try:
            sales = self.store.load()
            revenue = total_revenue(sales)
        except STORAGE_ERRORS as error:
            messagebox.showerror("Unable to load sales", str(error), parent=self)
            return
        self.sales = sales
        self.revenue_label.configure(text=f"Total Sales Revenue: {revenue:,.2f}")
        self.transactions_label.configure(text=f"Total Transactions: {len(sales)}")
        self.display_sales()

    def display_sales(self, *_):
        self.table.delete(*self.table.get_children())
        matches = filter_sales(self.sales, self.search_text.get(), self.sale_date)
        for row, sale in enumerate(reversed(matches)):
            self.table.insert("", "end", iid=sale.sale_id, tags=("Stripe",) if row % 2 else (), values=(
                sale.sale_id, sale.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                sale.product_id, sale.product_name, sale.quantity,
                f"{sale.unit_price:,.2f}", f"{sale.total_amount:,.2f}",
            ))

    def export_excel(self):
        save_excel(self, "StockMaster Sales.xlsx",
                   lambda path: export_sales(path, self.store.load()))

    def apply_date_filter(self):
        value = self.date_entry.get().strip()
        try:
            self.sale_date = date.fromisoformat(value) if value else None
            if value:
                self.date_entry.delete(0, "end")
                self.date_entry.insert(0, self.sale_date.isoformat())
        except ValueError:
            messagebox.showerror("Invalid date", "Enter a date as YYYY-MM-DD.", parent=self)
            return
        self.display_sales()

    def clear_date_filter(self):
        self.date_entry.delete(0, "end")
        self.apply_date_filter()

    def record_sale(self):
        try:
            products = self.store.products.load()
        except STORAGE_ERRORS as error:
            messagebox.showerror("Unable to load products", str(error), parent=self)
            return
        if not products:
            messagebox.showinfo("No products", "Add a product before recording a sale.", parent=self)
            return
        SaleDialog(self, products)


class SaleDialog(tk.Toplevel):
    """Preview a sale and submit it to the storage layer for final validation."""

    def __init__(self, page, products):
        super().__init__(page)
        self.page = page
        self.title("Record New Sale")
        self.transient(page.winfo_toplevel())

        form = ttk.Frame(self, padding=24)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Product").grid(row=0, column=0, sticky="w", pady=5)
        self.product_choice = ttk.Combobox(form, state="readonly", width=38)
        self.product_choice.grid(row=0, column=1, sticky="ew", padx=(16, 0), pady=5)
        self.product_choice.bind("<<ComboboxSelected>>", self.update_preview)

        self.product_id = tk.StringVar(self)
        self.stock = tk.StringVar(self)
        self.price = tk.StringVar(self)
        self.total = tk.StringVar(self)
        for row, label, variable in (
            (1, "Product ID", self.product_id), (2, "Available stock", self.stock),
            (3, "Unit selling price", self.price), (5, "Total sale amount", self.total),
        ):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Label(form, textvariable=variable).grid(row=row, column=1, sticky="w", padx=(16, 0))

        self.quantity = tk.StringVar(self)
        ttk.Label(form, text="Quantity to sell").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=self.quantity).grid(
            row=4, column=1, sticky="ew", padx=(16, 0), pady=5
        )
        self.quantity_trace = self.quantity.trace_add("write", self.update_preview)
        self.set_products(products)

        buttons = ttk.Frame(form)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(0, 8))
        ttk.Button(
            buttons, text="Confirm Sale", command=self.confirm, style="Primary.TButton"
        ).pack(side="left")
        self.bind("<Escape>", lambda event: self.destroy())
        self.wait_visibility()
        self.grab_set()
        self.product_choice.focus_set()

    def destroy(self):
        self.quantity.trace_remove("write", self.quantity_trace)
        super().destroy()

    def set_products(self, products, selected_id=None):
        self.products = products
        self.product_choice.configure(values=[
            f"{product.name} [{product.product_id}]" for product in products
        ])
        self.product_choice.set("")
        for index, product in enumerate(products):
            if product.product_id == selected_id:
                self.product_choice.current(index)
                break
        self.update_preview()

    def selected_product(self):
        index = self.product_choice.current()
        return self.products[index] if index >= 0 else None

    def update_preview(self, *_):
        product = self.selected_product()
        self.product_id.set(product.product_id if product else "-")
        self.stock.set(str(product.quantity) if product else "-")
        self.price.set(f"{product.selling_price:,.2f}" if product else "-")
        self.total.set("-")
        if product:
            try:
                quantity = parse_sale_quantity(self.quantity.get())
                self.total.set(f"{product.selling_price * quantity:,.2f}")
            except (ValueError, DecimalException):
                pass

    def confirm(self):
        product = self.selected_product()
        if product is None:
            messagebox.showerror("Unable to record sale", "Select a product first.", parent=self)
            return
        try:
            sale = self.page.store.record(product.product_id, self.quantity.get(), product.selling_price)
        except STORAGE_ERRORS as error:
            messagebox.showerror("Unable to record sale", str(error), parent=self)
            try:
                self.set_products(self.page.store.products.load(), product.product_id)
            except STORAGE_ERRORS:
                pass
            return
        self.destroy()
        self.page.refresh()
        messagebox.showinfo(
            "Sale recorded", f"Sale {sale.sale_id} was recorded for {sale.total_amount:,.2f}.",
            parent=self.page,
        )
