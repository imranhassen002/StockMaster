import csv
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from stockmaster.product_store import ProductStore
from stockmaster.products import inventory_summary, search_products, validate_product


VALID = {
    "name": "Café mugs, large",
    "category": "Kitchen",
    "unit_cost": "2.35",
    "selling_price": "4.50",
    "quantity": "10",
    "minimum_stock": "3",
}


class ProductTests(unittest.TestCase):
    def test_validation(self):
        invalid = {
            "name": ("", "  "),
            "category": ("", "  "),
            "unit_cost": ("-1", "NaN", "Infinity", "-Infinity", "abc"),
            "selling_price": ("-1", "NaN", "Infinity", "abc"),
            "quantity": ("-1", "1.5", "NaN", "Infinity"),
            "minimum_stock": ("-1", "2.0", "NaN", "Infinity"),
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_product("P1", dict(VALID, **{field: value}))

    def test_status_at_stock_boundaries(self):
        for quantity, expected in ((0, "Out of Stock"), (3, "Low Stock"), (4, "In Stock")):
            with self.subTest(quantity=quantity):
                product = validate_product("P1", dict(VALID, quantity=str(quantity)))
                self.assertEqual(product.stock_status, expected)

    def test_search_by_name_category_or_id(self):
        mug = validate_product("A12BC", VALID)
        pen = validate_product("D34EF", dict(VALID, name="Pen", category="Office"))
        for query in (" CAFÉ ", "kitchen", "12bc"):
            with self.subTest(query=query):
                self.assertEqual(search_products([mug, pen], query), [mug])
        self.assertEqual(search_products([mug, pen], ""), [mug, pen])
        self.assertEqual(search_products([mug, pen], "unknown"), [])


class ProductStoreTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "data" / "products.csv"
        self.store = ProductStore(self.path)

    def test_missing_and_empty_csv(self):
        self.assertFalse(self.path.exists())
        self.assertEqual(self.store.load(), [])
        self.assertTrue(self.path.is_file())
        self.path.write_bytes(b"")
        self.assertEqual(self.store.load(), [])
        product = self.store.add(VALID)
        self.assertEqual(self.store.load(), [product])

    def test_add_save_and_reopen(self):
        first = self.store.add(VALID)
        second = self.store.add(VALID)
        self.assertNotEqual(first.product_id, second.product_id)
        before = self.path.read_bytes()
        self.assertEqual(ProductStore(self.path).load(), [first, second])
        self.assertEqual(self.path.read_bytes(), before)
        with self.path.open(encoding="utf-8", newline="") as file:
            self.assertEqual(next(csv.DictReader(file))["name"], VALID["name"])

    def test_edit_delete_and_dashboard_totals(self):
        first = self.store.add(VALID)
        second = self.store.add(dict(VALID, quantity="0", minimum_stock="0"))
        self.assertEqual(inventory_summary(self.store.load()), (2, Decimal("23.50"), 1))
        edited = self.store.edit(first.product_id, dict(VALID, quantity="3", unit_cost="3.00"))
        self.assertEqual(edited.product_id, first.product_id)
        self.assertEqual(self.store.load(), [edited, second])
        self.assertEqual(inventory_summary(self.store.load()), (2, Decimal("9.00"), 2))
        self.store.delete(second.product_id)
        self.assertEqual(inventory_summary(self.store.load()), (1, Decimal("9.00"), 1))
        self.store.delete(first.product_id)
        self.assertEqual(inventory_summary(self.store.load()), (0, Decimal(0), 0))

    def test_failed_replacement_preserves_csv(self):
        product = self.store.add(VALID)
        with patch.object(Path, "replace", side_effect=OSError("File unavailable")):
            with self.assertRaises(OSError):
                self.store.delete(product.product_id)
        self.assertEqual(self.store.load(), [product])
        self.assertCountEqual(self.path.parent.iterdir(), [self.path, self.path.with_suffix(".lock")])

    def test_oversized_product_fields_leave_existing_csv_readable(self):
        product = self.store.add(VALID)
        before = self.path.read_bytes()
        invalid = dict(VALID, name="A" * (csv.field_size_limit() + 1))
        with self.assertRaisesRegex(ValueError, "CSV limit"):
            self.store.edit(product.product_id, invalid)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.load(), [product])

    def test_concurrent_writes_preserve_all_products(self):
        self.store.load()
        with ThreadPoolExecutor(max_workers=4) as workers:
            products = list(workers.map(
                lambda index: ProductStore(self.path).add(dict(VALID, name=f"Product {index}")),
                range(8),
            ))
        self.assertCountEqual(self.store.load(), products)

    def test_bad_csv_is_preserved(self):
        self.store.load()
        self.path.write_text("broken,header\n", encoding="utf-8")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "invalid header"):
            self.store.add(VALID)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
