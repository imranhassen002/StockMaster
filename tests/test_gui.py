import tkinter as tk
import unittest
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import ttk
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from stockmaster.app import StockMasterApp
from stockmaster.csv_storage import write_csv
from stockmaster.excel_service import PRODUCT_COLUMNS
from stockmaster.pages.analytics import AnalyticsPage
from stockmaster.pages.dashboard import DashboardPage
from stockmaster.pages.excel_dialogs import ProductImportReview
from stockmaster.pages.products import ProductDialog, ProductsPage
from stockmaster.pages.sales import SaleDialog, SalesPage
from stockmaster.product_store import ProductStore
from stockmaster.products import validate_product
from stockmaster.sales import SALE_FIELDS


PRODUCT = {
    "name": "USB-C cable", "category": "Accessories", "unit_cost": "2.50",
    "selling_price": "7.50", "quantity": "8", "minimum_stock": "3",
}


def find_button(parent, label):
    for widget in parent.winfo_children():
        if isinstance(widget, ttk.Button) and widget["text"] == label:
            return widget
        match = find_button(widget, label)
        if match is not None:
            return match
    return None


def set_entry(entry, value):
    entry.delete(0, "end")
    entry.insert(0, value)


class StockMasterGUITests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        self.store = ProductStore(self.directory / "products.csv")
        self.callback_errors = []
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            if any(message in str(error) for message in (
                "no display name", "couldn't connect to display", "usable init.tcl",
            )):
                self.skipTest(f"Tk display unavailable: {str(error).splitlines()[0]}")
            raise
        self.addCleanup(self.assertEqual, self.callback_errors, [])
        self.addCleanup(self.root.destroy)
        self.root.report_callback_exception = lambda kind, value, _tb: (
            self.callback_errors.append(f"{kind.__name__}: {value}")
        )
        self.app = StockMasterApp(self.root, self.store)
        self.root.update()

    def navigate(self, page_type):
        self.app.navigation_buttons[page_type].invoke()
        self.root.update()
        self.assertEqual(self.app.header_title["text"], page_type.title)
        self.assertTrue(self.app.navigation_buttons[page_type].instate(["selected"]))
        return self.app.current_page

    def click(self, page, label):
        button = find_button(page, label)
        self.assertIsNotNone(button, f"Missing button: {label}")
        button.invoke()
        self.root.update()

    def dialog(self, page, dialog_type):
        return next(child for child in page.winfo_children() if isinstance(child, dialog_type))

    def card_values(self, page):
        return tuple(label["text"] for label in page.values)

    def test_product_crud_search_validation_and_scrollbars(self):
        page = self.navigate(ProductsPage)
        self.assertEqual(page.table.get_children(), ())
        self.click(page, "Add Product")
        form = self.dialog(page, ProductDialog)
        with patch("stockmaster.pages.products.messagebox.showerror") as error:
            self.click(form, "Save")
            self.assertIn("Product Name is required", error.call_args.args[1])
        long_name = "Braided USB-C cable with reinforced connector " * 4 + "extra long"
        for field, value in dict(PRODUCT, name=long_name).items():
            set_entry(form.entries[field], value)
        self.click(form, "Save")
        product_id, = page.table.get_children()
        self.assertEqual(page.table.set(product_id, "Product Name"), long_name)
        page.search_text.set("extra long")
        self.assertEqual(page.table.get_children(), (product_id,))
        page.search_text.set("unmatched")
        self.assertEqual(page.table.get_children(), ())
        page.search_text.set("")
        page.table.selection_set(product_id)
        self.click(page, "Edit Product")
        form = self.dialog(page, ProductDialog)
        self.assertEqual(form.entries["name"].get(), long_name)
        set_entry(form.entries["quantity"], "2")
        self.click(form, "Save")
        self.assertEqual(page.table.set(product_id, "Stock Status"), "Low Stock")
        page.table.selection_set(product_id)
        with patch("stockmaster.pages.products.messagebox.askyesno", return_value=False):
            self.click(page, "Delete Product")
        self.assertTrue(page.table.exists(product_id))
        with patch("stockmaster.pages.products.messagebox.askyesno", return_value=True):
            self.click(page, "Delete Product")
        self.assertEqual(self.store.load(), [])

        self.store.import_products([
            validate_product(f"TEMP-{index}", dict(PRODUCT, name=f"Cable {index}"))
            for index in range(20)
        ])
        self.click(page, "Refresh")
        self.root.geometry("740x480")
        self.root.update()
        self.assertEqual(len(page.table.get_children()), 20)
        self.assertLess(page.table.xview()[1], 1)
        self.assertLess(page.table.yview()[1], 1)
        for scroll in (page.table.xview_moveto, page.table.yview_moveto):
            scroll(1)
        self.root.update()
        self.assertAlmostEqual(page.table.xview()[1], 1)
        self.assertAlmostEqual(page.table.yview()[1], 1)

    def test_sale_validation_dashboard_history_and_restart(self):
        self.assertEqual(self.card_values(self.app.current_page), ("0", "0.00", "0.00", "0"))
        product = self.store.add(PRODUCT)
        page = self.navigate(SalesPage)
        self.assertEqual(page.table.get_children(), ())
        self.click(page, "Record New Sale")
        dialog = self.dialog(page, SaleDialog)
        dialog.product_choice.current(0)
        dialog.quantity.set("9")
        with patch("stockmaster.pages.sales.messagebox.showerror") as error:
            self.click(dialog, "Confirm Sale")
            self.assertIn("Only 8 units", error.call_args.args[1])
        self.assertEqual(self.store.load()[0].quantity, 8)
        dialog.quantity.set("5")
        self.assertEqual(dialog.total.get(), "37.50")
        with patch("stockmaster.pages.sales.messagebox.showinfo") as notice:
            self.click(dialog, "Confirm Sale")
            notice.assert_called_once()
        sale_id, = page.table.get_children()
        self.assertEqual(page.table.set(sale_id, "Total Amount"), "37.50")
        self.assertEqual(self.navigate(ProductsPage).table.set(product.product_id, "Quantity"), "3")
        self.assertEqual(self.card_values(self.navigate(DashboardPage)), ("1", "7.50", "37.50", "1"))

        paths = (self.store.path, self.app.sale_store.path)
        before = [path.read_bytes() for path in paths]
        restarted = tk.Tk()
        try:
            app = StockMasterApp(restarted, ProductStore(self.store.path))
            self.assertEqual(self.card_values(app.current_page), ("1", "7.50", "37.50", "1"))
            app.show_page(SalesPage)
            self.assertEqual(app.current_page.table.get_children(), (sale_id,))
        finally:
            restarted.destroy()
        self.assertEqual([path.read_bytes() for path in paths], before)

    def test_analytics_charts_refresh_date_filter_and_resizing(self):
        page = self.navigate(AnalyticsPage)
        self.assertEqual(self.card_values(page), ("0.00", "0", "0", "0.00"))
        self.assertIn("No sales data", page.status["text"])
        self.assertEqual(page.column_count, 4)
        name = "USB-C docking station with a reinforced housing and adjustable cable mount"
        product = self.store.add(dict(PRODUCT, name=name))
        other = self.store.add(dict(PRODUCT, name="Small adapter", category="Adapters"))
        old = self.app.sale_store.record(product.product_id, "2")
        recent = self.app.sale_store.record(other.product_id, "1")
        old = replace(old, timestamp=old.timestamp - timedelta(days=40))
        write_csv(self.app.sale_store.path, SALE_FIELDS, map(asdict, (old, recent)))
        self.click(page, "Refresh Analytics")
        self.assertEqual(self.card_values(page), ("22.50", "2", "3", "11.25"))
        self.assertEqual(len(page.revenue_chart.axes.lines[0].get_xdata()), 2)
        self.assertEqual(len(page.products_chart.axes.patches), 2)
        labels = [tick.get_text().replace("\n", " ") for tick in page.products_chart.axes.get_yticklabels()]
        self.assertEqual(labels[0], name)
        self.assertEqual(len(page.inventory_chart.axes.patches), 2)
        inventory_slice = page.inventory_chart.axes.patches[0]
        page.date_range.set("Last 7 Days")
        page.date_range.event_generate("<<ComboboxSelected>>")
        self.root.update()
        self.assertEqual(self.card_values(page), ("7.50", "1", "1", "7.50"))
        self.assertIs(page.inventory_chart.axes.patches[0], inventory_slice)
        self.assertIn("Maximum  1", page.transaction_stats["text"])

        page.date_range.set("All Time")
        page.date_range.event_generate("<<ComboboxSelected>>")
        self.root.geometry("740x480")
        self.root.update()
        self.assertEqual(page.column_count, 2)
        self.assertLess(page.viewport.yview()[1], 1)
        page.viewport.yview_moveto(1)
        self.assertAlmostEqual(page.viewport.yview()[1], 1)
        chart = page.products_chart
        renderer = chart.canvas.get_renderer()
        boxes = [text.get_window_extent(renderer) for text in chart.axes.get_yticklabels()]
        self.assertFalse(boxes[0].overlaps(boxes[1]))
        for box in boxes:
            self.assertGreaterEqual(box.x0, 0)
            self.assertLessEqual(box.x1, chart.figure.bbox.width)

    def test_excel_buttons_import_cancel_and_report_preserve_records(self):
        product = self.store.add(PRODUCT)
        sale = self.app.sale_store.record(product.product_id, "1")
        import_path = self.directory / "import.xlsx"
        workbook = Workbook()
        workbook.active.append(PRODUCT_COLUMNS)
        workbook.active.append(["0007", "Imported", "Tools", 1, 3, 2, 1])
        workbook.active.append([product.product_id, "Duplicate", "Tools", 1, 3, 2, 1])
        workbook.save(import_path)
        workbook.close()

        page = self.navigate(ProductsPage)
        before = self.store.path.read_bytes()
        with patch("stockmaster.pages.products.filedialog.askopenfilename", return_value=str(import_path)):
            self.click(page, "Import from Excel")
            review = self.dialog(page, ProductImportReview)
            self.assertEqual((len(review.preview.valid), len(review.preview.duplicates)), (1, 1))
            self.click(review, "Cancel")
            self.assertEqual(self.store.path.read_bytes(), before)
            self.click(page, "Import from Excel")
            with patch("stockmaster.pages.excel_dialogs.messagebox.showinfo"):
                self.click(self.dialog(page, ProductImportReview), "Import Valid Products")
        self.assertTrue(page.table.exists("0007"))

        paths = (self.store.path, self.app.sale_store.path)
        before = [path.read_bytes() for path in paths]
        for page_type, button, sheet, count in (
            (ProductsPage, "Export to Excel", "Inventory", 1),
            (SalesPage, "Export Sales", "Sales History", 1),
            (AnalyticsPage, "Generate Excel Report", "Business Summary", 5),
        ):
            page = self.navigate(page_type)
            output_path = self.directory / f"{sheet}.xlsx"
            with patch("stockmaster.pages.excel_dialogs.filedialog.asksaveasfilename",
                       return_value=str(output_path)), patch("stockmaster.pages.excel_dialogs.messagebox.showinfo"):
                self.click(page, button)
            with output_path.open("rb") as file:
                workbook = load_workbook(file, read_only=True)
                self.assertEqual(len(workbook.sheetnames), count)
                if sheet == "Sales History":
                    self.assertEqual(workbook[sheet]["A2"].value, sale.sale_id)
                workbook.close()
        self.assertEqual([path.read_bytes() for path in paths], before)
