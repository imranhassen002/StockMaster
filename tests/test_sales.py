import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from stockmaster.product_store import ProductStore
from stockmaster.products import inventory_summary
from stockmaster.sale_store import SaleStore
from stockmaster.sales import filter_sales, total_revenue


PRODUCT = {
    "name": "Laptop", "category": "Computers", "unit_cost": "0.05",
    "selling_price": "0.10", "quantity": "10", "minimum_stock": "3",
}


class SaleStoreTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.products = ProductStore(Path(folder.name) / "products.csv")
        self.sales = SaleStore(self.products)
        self.product = self.products.add(PRODUCT)

    def record(self, quantity="2"):
        return self.sales.record(self.product.product_id, quantity)

    def test_valid_sales_update_inventory_and_dashboard_totals(self):
        self.assertFalse(self.sales.path.exists())
        self.assertEqual(self.sales.load(), [])
        self.assertTrue(self.sales.path.is_file())
        first = self.record()
        second = self.record("5")
        self.assertNotEqual(first.sale_id, second.sale_id)
        self.assertEqual(first.total_amount, Decimal("0.20"))
        products, history = self.sales.load_dashboard_data()
        self.assertEqual(history, [first, second])
        self.assertEqual(len(history), 2)
        self.assertEqual(total_revenue(history), Decimal("0.70"))
        self.assertEqual(inventory_summary(products), (1, Decimal("0.15"), 1))
        self.assertEqual(products[0].quantity, 3)
        self.assertEqual(products[0].stock_status, "Low Stock")

    def test_invalid_quantities_and_out_of_stock(self):
        for quantity in ("0", "-1", "", "2.5", "NaN", "Infinity", "abc"):
            with self.subTest(quantity=quantity), self.assertRaisesRegex(ValueError, "positive"):
                self.record(quantity)
        with self.assertRaisesRegex(ValueError, "Only 10"):
            self.record("11")
        self.assertEqual(self.sales.load(), [])
        self.assertEqual(self.products.load(), [self.product])
        self.record("10")
        with self.assertRaisesRegex(ValueError, "out of stock"):
            self.record("1")
        self.assertEqual(self.products.load()[0].quantity, 0)

    def test_missing_selection_or_removed_product(self):
        with self.assertRaisesRegex(ValueError, "Select a product"):
            self.sales.record("", "2")
        self.products.delete(self.product.product_id)
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            self.record()
        self.assertEqual(self.sales.load(), [])

    def test_price_change_requires_review(self):
        self.products.edit(self.product.product_id, dict(PRODUCT, selling_price="0.30"))
        with self.assertRaisesRegex(ValueError, "price changed"):
            self.sales.record(self.product.product_id, "2", expected_price=Decimal("0.10"))
        self.assertEqual(self.sales.load(), [])
        self.assertEqual(self.products.load()[0].quantity, 10)

    def test_stale_product_form_cannot_overwrite_stock_after_sale(self):
        self.record()
        with self.assertRaisesRegex(ValueError, "product changed"):
            self.products.edit(self.product.product_id, PRODUCT, expected_product=self.product)
        self.assertEqual(self.products.load()[0].quantity, 8)

    def test_history_survives_edit_delete_and_reopen(self):
        sale = self.record()
        self.products.edit(self.product.product_id, dict(PRODUCT, name="Renamed", selling_price="0.99"))
        self.products.delete(self.product.product_id)
        history = SaleStore(ProductStore(self.products.path)).load()
        self.assertEqual(history, [sale])
        self.assertEqual(history[0].product_name, "Laptop")
        self.assertEqual(history[0].unit_price, Decimal("0.10"))
        self.assertEqual(history[0].quantity, 2)
        self.assertEqual(history[0].total_amount, Decimal("0.20"))
        self.assertIsNotNone(history[0].timestamp.utcoffset())

    def test_search_and_date_filter_leave_csv_unchanged(self):
        sale = self.record()
        before = self.sales.path.read_bytes()
        history = self.sales.load()
        for query in ("  lAp  ", sale.sale_id.lower(), sale.product_id.lower()):
            self.assertEqual(filter_sales(history, query, sale.timestamp.date()), [sale])
        self.assertEqual(filter_sales(history, "missing"), [])
        self.assertEqual(filter_sales(history, "", sale.timestamp.date() - timedelta(days=1)), [])
        self.assertEqual(self.sales.path.read_bytes(), before)

    def test_inventory_write_failure_preserves_both_files(self):
        self.sales.load()
        with patch.object(self.products, "_save", side_effect=OSError("Inventory unavailable")):
            with self.assertRaisesRegex(OSError, "Inventory unavailable"):
                self.record()
        self.assertEqual(self.products.load(), [self.product])
        self.assertEqual(self.sales.load(), [])
        self.assertFalse(self.products.sale_journal.exists())

    def test_sales_write_failure_rolls_back_stock(self):
        first = self.record()
        before = self.sales.path.read_bytes()
        with patch.object(self.sales, "_save", side_effect=OSError("Sales unavailable")):
            with self.assertRaisesRegex(OSError, "Sales unavailable"):
                self.record()
        self.assertEqual(self.products.load()[0].quantity, 8)
        self.assertEqual(self.sales.load(), [first])
        self.assertEqual(self.sales.path.read_bytes(), before)
        self.assertFalse(self.products.sale_journal.exists())

    def test_validation_error_during_sales_write_restores_inventory(self):
        with patch.object(self.sales, "_save", side_effect=ValueError("CSV field exceeds limit")):
            with self.assertRaisesRegex(ValueError, "CSV field exceeds limit"):
                self.record()
        self.assertFalse(self.products.sale_journal.exists())
        self.assertEqual(self.products.load(), [self.product])
        self.assertEqual(self.sales.load(), [])

    def test_error_after_commit_returns_the_confirmed_sale(self):
        original_save = self.sales._save

        def fail_after_commit(history):
            original_save(history)
            raise OSError("Error after CSV replacement")

        with patch.object(self.sales, "_save", side_effect=fail_after_commit):
            sale = self.record()
        self.assertEqual(self.sales.load(), [sale])
        self.assertEqual(self.products.load()[0].quantity, 8)
        self.assertFalse(self.products.sale_journal.exists())

    def test_failed_rollback_recovers_on_reopen(self):
        original_save = self.products._save

        def fail_rollback(products):
            if products[0].quantity == self.product.quantity:
                raise OSError("Rollback unavailable")
            original_save(products)

        with patch.object(self.sales, "_save", side_effect=OSError("Sales unavailable")), \
             patch.object(self.products, "_save", side_effect=fail_rollback):
            with self.assertRaisesRegex(OSError, "Recovery is pending"):
                self.record()
        self.assertTrue(self.products.sale_journal.exists())
        self.assertIn(",8,", self.products.path.read_text(encoding="utf-8"))
        reopened = SaleStore(ProductStore(self.products.path))
        self.assertEqual(reopened.load_dashboard_data(), ([self.product], []))
        self.assertFalse(self.products.sale_journal.exists())

    def test_committed_journal_keeps_sale_and_reduced_stock(self):
        sale = self.record()
        journal = {
            "sale_id": sale.sale_id, "product_id": sale.product_id,
            "old_quantity": 10, "new_quantity": 8,
        }
        self.products.sale_journal.write_text(json.dumps(journal), encoding="utf-8")
        products, sales = SaleStore(ProductStore(self.products.path)).load_dashboard_data()
        self.assertEqual(sales, [sale])
        self.assertEqual(products[0].quantity, 8)
        self.assertFalse(self.products.sale_journal.exists())

    def test_concurrent_sales_recheck_stock(self):
        def buy(_):
            try:
                return SaleStore(ProductStore(self.products.path)).record(self.product.product_id, "6")
            except ValueError as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(buy, range(2)))
        self.assertIn("Only 4 units are currently available.", results)
        self.assertEqual(len(self.sales.load()), 1)
        self.assertEqual(self.products.load()[0].quantity, 4)
