import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from stockmaster.excel_service import (
    MONEY_FORMAT, PRODUCT_COLUMNS, SALES_COLUMNS, export_products, export_sales,
    generate_report, review_product_import,
)
from stockmaster.product_store import ProductStore
from stockmaster.sale_store import SaleStore


PRODUCT = {
    "name": "Cable", "category": "Electronics", "unit_cost": "0.50",
    "selling_price": "2.25", "quantity": "8", "minimum_stock": "2",
}


class ExcelTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        self.products = ProductStore(self.directory / "products.csv")
        self.sales = SaleStore(self.products)
        self.path = self.directory / "output.xlsx"

    def workbook(self, rows, headers=PRODUCT_COLUMNS):
        workbook = Workbook()
        workbook.active.append(headers)
        for row in rows:
            workbook.active.append(row)
        workbook.save(self.path)
        workbook.close()

    def open_output(self):
        # A binary handle lets the file close promptly on Windows.
        with self.path.open("rb") as file:
            return load_workbook(file, data_only=False)

    def test_product_export_formats_columns_and_preserves_literal_text(self):
        original = self.products.add(dict(PRODUCT, name="=1+1", category="@Home"))
        before = self.products.path.read_bytes()
        export_products(self.path, [original])
        sheet = self.open_output()["Inventory"]
        self.assertEqual(tuple(cell.value for cell in sheet[1]), PRODUCT_COLUMNS)
        self.assertEqual(sheet["A2"].value, original.product_id)
        self.assertEqual(sheet["B2"].value, "=1+1")
        self.assertEqual(sheet["B2"].data_type, "s")
        self.assertEqual(sheet["C2"].value, "@Home")
        self.assertEqual(sheet["D2"].value, 0.5)
        self.assertEqual(sheet["D2"].number_format, MONEY_FORMAT)
        self.assertTrue(sheet["A1"].font.bold)
        self.assertEqual(sheet["A1"].fill.fgColor.rgb[-6:], "14233D")
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertEqual(sheet.auto_filter.ref, "A1:H2")
        self.assertEqual(self.products.path.read_bytes(), before)
        preview = review_product_import(self.path, [])
        # The regex rule rejects formula-like names such as "=1+1" on import.
        self.assertEqual(preview.valid, [])
        self.assertIn("Invalid Excel product data", preview.invalid[0][1])

    def test_review_mixed_rows_and_commit_only_valid_new_products(self):
        existing = self.products.add(PRODUCT)
        self.workbook([
            ("0010", "New", "NA", 0.25, 1.50, 0, 3, "In Stock"),
            ("", "Generated", "Tools", 0, 0, 2.0, 2, ""),
            (existing.product_id.lower(), "Existing", "Tools", 0, 0, 0, 0, ""),
            ("0010", "Repeated", "Tools", 0, 0, 0, 0, ""),
            ("0003", "", "Tools", 0, 1, 3, 0, ""),
            ("0004", "Broken", "Tools", "NaN", 1, 3, 0, ""),
            ("0005", "Broken", "Tools", 1, "Infinity", 3, 0, ""),
            ("0006", "Broken", "Tools", 1, 1, 1.5, 0, ""),
            ("0007", "Broken", "Tools", "=1+1", 1, 1, 0, ""),
            (),
        ])
        before = self.products.path.read_bytes()
        preview = review_product_import(self.path, self.products.load())
        self.assertEqual([row for row, _ in preview.invalid], [6, 7, 8, 9, 10])
        self.assertEqual([row for row, _ in preview.duplicates], [4, 5])
        self.assertEqual(len(preview.valid), 2)
        self.assertEqual(self.products.path.read_bytes(), before)

        first, second = self.products.import_products(preview.valid)
        self.assertEqual(first.product_id, "0010")
        self.assertEqual(first.category, "NA")
        self.assertEqual(first.stock_status, "Out of Stock")
        self.assertEqual(second.stock_status, "Low Stock")
        self.assertTrue(second.product_id)
        self.assertEqual(len({existing.product_id, first.product_id, second.product_id}), 3)
        self.assertEqual(ProductStore(self.products.path).load(), [existing, first, second])

    def test_optional_id_column_and_invalid_workbook(self):
        self.workbook([("Clamp", "Tools", 1, 2, 3, 4)], headers=PRODUCT_COLUMNS[1:-1])
        self.assertEqual(review_product_import(self.path, []).valid[0].product_id, "")
        self.workbook([], headers=["Product Name"])
        with self.assertRaisesRegex(ValueError, "Missing required columns"):
            review_product_import(self.path, [])
        self.path.write_text("invalid .xlsx", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, r"valid \.xlsx"):
            review_product_import(self.path, [])

    def test_import_conflict_after_preview_and_failed_write_do_not_change_csv(self):
        existing = self.products.add(PRODUCT)
        self.workbook([("NEW", "Other", "Tools", 1, 2, 3, 4, "")])
        preview = review_product_import(self.path, [existing])
        before = self.products.path.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("Cannot replace CSV")):
            with self.assertRaises(PermissionError):
                self.products.import_products(preview.valid)
        self.assertEqual(self.products.path.read_bytes(), before)
        self.products.import_products(preview.valid)
        before = self.products.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "already in use"):
            self.products.import_products([replace(preview.valid[0], product_id="OTHER"), *preview.valid])
        self.assertEqual(self.products.path.read_bytes(), before)

    def test_sales_export_uses_historical_values(self):
        product = self.products.add(dict(PRODUCT, name="+Widget"))
        sale = self.sales.record(product.product_id, "2")
        self.products.edit(product.product_id, dict(PRODUCT, name="Renamed", selling_price="99"))
        before = self.sales.path.read_bytes()
        export_sales(self.path, self.sales.load())
        sheet = self.open_output()["Sales History"]
        self.assertEqual(tuple(cell.value for cell in sheet[1]), SALES_COLUMNS)
        self.assertEqual([cell.value for cell in sheet[2]], [
            sale.sale_id, sale.timestamp.isoformat(sep=" "), product.product_id,
            "+Widget", 2, 2.25, 4.50,
        ])
        self.assertEqual(sheet["D2"].data_type, "s")
        self.assertEqual(sheet["G2"].number_format, MONEY_FORMAT)
        self.assertEqual(self.sales.path.read_bytes(), before)

    def test_all_time_report_and_summary(self):
        product = self.products.add(dict(PRODUCT, category="=Category"))
        old_sale = self.sales.record(product.product_id, "2")
        current = self.products.load()[0]
        self.products.edit(product.product_id, dict(PRODUCT, name="Renamed", quantity=str(current.quantity)))
        self.sales.record(product.product_id, "1")
        products, sales = self.sales.load_dashboard_data()
        generate_report(self.path, products, sales)
        workbook = self.open_output()
        self.assertEqual(workbook.sheetnames, [
            "Business Summary", "Inventory", "Sales History", "Product Performance", "Category Summary",
        ])
        summary = workbook["Business Summary"]
        self.assertTrue(summary["A2"].value.startswith("Generated: "))
        self.assertIn("All-time sales and current inventory", summary["A3"].value)
        self.assertEqual([summary[f"B{row}"].value for row in range(5, 12)], [1, 2.5, 6.75, 2, 3, 3.375, 0])
        self.assertEqual(summary["B10"].number_format, MONEY_FORMAT)
        self.assertEqual(workbook["Sales History"]["A2"].value, old_sale.sale_id)
        self.assertEqual([cell.value for cell in workbook["Product Performance"][2]],
                         [product.product_id, "Renamed", 3, 6.75])
        categories = {row[0].value: [cell.value for cell in row[1:]]
                      for row in list(workbook["Category Summary"].rows)[1:]}
        self.assertEqual(categories, {"Electronics": [5, 2.5]})

    def test_empty_exports_and_failed_replacement_preserves_workbook(self):
        export_products(self.path, [])
        self.assertEqual(self.open_output()["Inventory"].max_row, 1)
        export_sales(self.path, [])
        self.assertEqual(self.open_output()["Sales History"].max_row, 1)
        generate_report(self.path, *self.sales.load_dashboard_data())
        workbook = self.open_output()
        self.assertEqual(workbook["Product Performance"].max_row, 1)
        self.assertEqual(workbook["Category Summary"].max_row, 1)
        self.assertEqual(workbook["Business Summary"]["B7"].value, 0)
        before = self.path.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("Workbook is open")):
            with self.assertRaises(PermissionError):
                export_products(self.path, [])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.directory.glob("*.xlsx")), [self.path])

    def test_excel_cell_limit_does_not_truncate_or_replace_file(self):
        export_products(self.path, [])
        before = self.path.read_bytes()
        product = self.products.add(dict(PRODUCT, name="A" * 32768))
        with self.assertRaisesRegex(ValueError, "cell length limit"):
            export_products(self.path, [product])
        self.assertEqual(self.path.read_bytes(), before)

    def test_excel_does_not_silently_turn_tiny_prices_into_zero(self):
        export_products(self.path, [])
        before = self.path.read_bytes()
        product = self.products.add(dict(PRODUCT, unit_cost="1E-400"))
        with self.assertRaisesRegex(ValueError, "too small for Excel"):
            export_products(self.path, [product])
        self.assertEqual(self.path.read_bytes(), before)
