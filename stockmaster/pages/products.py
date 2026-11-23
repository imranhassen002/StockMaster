import csv
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from stockmaster.excel_service import export_products, review_product_import
from stockmaster.pages.excel_dialogs import EXCEL_ERRORS, EXCEL_TYPES, ProductImportReview
from stockmaster.pages.excel_dialogs import save_excel, show_excel_error
from stockmaster.products import EDITABLE_FIELDS, search_products
from stockmaster.regex_validation import validate_product_name, validate_category


LOW_BACKGROUND, LOW_TEXT = "#FFF1D6", "#8A5300"
OUT_BACKGROUND, OUT_TEXT = "#FDE2E2", "#9B1C1C"


class ProductsPage(ttk.Frame):
    title = "Products"
    columns = (
        ("Product ID", 120, "w"),
        ("Product Name", 190, "w"),
        ("Category", 105, "w"),
        ("Unit Cost", 95, "e"),
        ("Selling Price", 100, "e"),
        ("Quantity", 70, "e"),
        ("Minimum Stock", 105, "e"),
        ("Stock Status", 105, "w"),
    )

    def __init__(self, parent, store):
        super().__init__(parent, padding=28)
        self.store = store
        self.products = {}
        self.search_text = tk.StringVar(self)

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 12))
        actions = (
            ("Add Product", self.add_product),
            ("Edit Product", self.edit_product),
            ("Delete Product", self.delete_product),
            ("Refresh", self.refresh),
        )
        for text, action in actions:
            style = "Primary.TButton" if text == "Add Product" else "TButton"
            ttk.Button(toolbar, text=text, command=action, style=style).pack(
                side="left", padx=(0, 8)
            )

        excel_actions = ttk.Frame(self)
        excel_actions.pack(fill="x", pady=(0, 12))
        ttk.Button(excel_actions, text="Import from Excel", style="Primary.TButton",
                   command=self.import_excel).pack(side="left", padx=(0, 8))
        ttk.Button(excel_actions, text="Export to Excel", style="Primary.TButton",
                   command=self.export_excel).pack(side="left")

        search_bar = ttk.Frame(self)
        search_bar.pack(fill="x", pady=(0, 12))
        ttk.Label(search_bar, text="Search by name, category, or ID").pack(side="left")
        ttk.Entry(search_bar, textvariable=self.search_text).pack(
            side="left", fill="x", expand=True, padx=(12, 0)
        )

        info_bar = ttk.Frame(self)
        info_bar.pack(fill="x", pady=(0, 8))
        self.count_label = ttk.Label(info_bar, style="Muted.TLabel")
        self.count_label.pack(side="left")
        # Colour legend that matches the row highlighting in the table.
        for text, background, foreground in (
            ("Out of Stock", OUT_BACKGROUND, OUT_TEXT), ("Low Stock", LOW_BACKGROUND, LOW_TEXT),
        ):
            tk.Label(info_bar, text=text, background=background, foreground=foreground,
                     font=("Segoe UI", 9, "bold"), padx=8, pady=2).pack(side="right", padx=(6, 0))

        table_frame = ttk.Frame(self, style="Surface.TFrame")
        table_frame.pack(fill="both", expand=True)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        headings = [heading for heading, _, _ in self.columns]
        self.table = ttk.Treeview(
            table_frame, columns=headings, show="headings", selectmode="browse"
        )
        self.table.grid(row=0, column=0, sticky="nsew")
        for heading, width, anchor in self.columns:
            self.table.heading(heading, text=heading, anchor=anchor)
            self.table.column(heading, width=width, minwidth=width, anchor=anchor)
        vertical = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        # Highlight rows that need restocking: orange for low stock, red for out of stock.
        self.table.tag_configure("Low Stock", background=LOW_BACKGROUND, foreground=LOW_TEXT)
        self.table.tag_configure("Out of Stock", background=OUT_BACKGROUND, foreground=OUT_TEXT)
        # Light stripes on alternate in-stock rows make long tables easier to read.
        self.table.tag_configure("Stripe", background="#F5F8FC")

        self.search_trace = self.search_text.trace_add("write", self.display_products)
        self.refresh()

    def destroy(self):
        self.search_text.trace_remove("write", self.search_trace)
        super().destroy()

    def display_products(self, *_):
        selected = self.table.selection()
        self.table.delete(*self.table.get_children())
        matches = search_products(self.products.values(), self.search_text.get())
        for row, product in enumerate(matches):
            tag = product.stock_status
            if tag == "In Stock" and row % 2:
                tag = "Stripe"
            self.table.insert("", "end", iid=product.product_id, values=(
                product.product_id, product.name, product.category,
                f"{product.unit_cost:,.2f}", f"{product.selling_price:,.2f}", product.quantity,
                product.minimum_stock, product.stock_status,
            ), tags=(tag,))
        self.count_label.configure(text=f"Showing {len(matches)} of {len(self.products)} products")
        if selected and self.table.exists(selected[0]):
            self.table.selection_set(selected[0])

    def refresh(self):
        try:
            products = self.store.load()
        except (OSError, ValueError, csv.Error) as error:
            messagebox.showerror("Unable to load products", str(error), parent=self)
            return
        self.products = {product.product_id: product for product in products}
        self.display_products()

    def export_excel(self):
        save_excel(self, "StockMaster Products.xlsx",
                   lambda path: export_products(path, self.store.load()))

    def import_excel(self):
        path = filedialog.askopenfilename(parent=self, filetypes=EXCEL_TYPES)
        if not path:
            return
        try:
            preview = review_product_import(path, self.store.load())
        except EXCEL_ERRORS as error:
            show_excel_error(self, "Unable to open product import", error)
            return
        ProductImportReview(self, preview)

    def selected_product(self):
        selection = self.table.selection()
        if selection:
            return self.products[selection[0]]
        messagebox.showinfo("Select a product", "Select a product from the table first.", parent=self)
        return None

    def add_product(self):
        ProductDialog(self, self.store.add)

    def edit_product(self):
        product = self.selected_product()
        if product is not None:
            ProductDialog(
                self,
                lambda values: self.store.edit(product.product_id, values, expected_product=product),
                product,
            )

    def delete_product(self):
        product = self.selected_product()
        if product is None:
            return
        confirmed = messagebox.askyesno(
            "Delete product", f'Delete "{product.name}" ({product.product_id})?',
            parent=self, default="no",
        )
        if not confirmed:
            return
        try:
            self.store.delete(product.product_id)
        except (OSError, ValueError, csv.Error) as error:
            messagebox.showerror("Unable to delete product", str(error), parent=self)
            return
        self.refresh()


class ProductDialog(tk.Toplevel):
    """Use the same form for adding and editing products."""

    def __init__(self, page, save_product, product=None):
        super().__init__(page)
        self.page = page
        self.save_product = save_product
        self.title("Add Product" if product is None else "Edit Product")
        self.transient(page.winfo_toplevel())

        form = ttk.Frame(self, padding=24)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)
        self.entries = {}
        for row, (field, label) in enumerate(EDITABLE_FIELDS):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=5)
            entry = ttk.Entry(form, width=28)
            entry.grid(row=row, column=1, sticky="ew", padx=(16, 0), pady=5)
            if product is not None:
                entry.insert(0, str(getattr(product, field)))
            self.entries[field] = entry

        buttons = ttk.Frame(form)
        buttons.grid(row=len(EDITABLE_FIELDS), column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Save", command=self.save, style="Primary.TButton").pack(side="left")
        self.bind("<Escape>", lambda event: self.destroy())
        self.bind("<Return>", lambda event: self.save())
        self.wait_visibility()
        self.grab_set()
        self.entries["name"].focus_set()

    def save(self):
        values = {field: entry.get() for field, entry in self.entries.items()}
        # Regex check for typed names and categories. Empty fields are left to
        # validate_product, which shows the "is required" message.
        try:
            if values["name"].strip():
                values["name"] = validate_product_name(values["name"])
            if values["category"].strip():
                values["category"] = validate_category(values["category"])
        except ValueError as error:
            messagebox.showerror("Invalid Product", str(error), parent=self)
            return
        try:
            self.save_product(values)
        except (OSError, ValueError, csv.Error) as error:
            messagebox.showerror("Unable to save product", str(error), parent=self)
            return
        self.destroy()
        self.page.refresh()
