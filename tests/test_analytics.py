import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from stockmaster.analytics import build_report, load_analytics_data
from stockmaster.csv_storage import write_csv
from stockmaster.product_store import ProductStore
from stockmaster.products import PRODUCT_FIELDS
from stockmaster.sale_store import SaleStore
from stockmaster.sales import SALE_FIELDS


def sale(sale_id, product_id, name, timestamp, quantity, total):
    return dict(
        sale_id=sale_id, timestamp=timestamp, product_id=product_id, product_name=name,
        quantity=quantity, unit_price=Decimal(total) / quantity, total_amount=total,
    )


def product(product_id, category, quantity):
    return dict(
        product_id=product_id, name=f"Product {product_id}", category=category,
        unit_cost="0.25", selling_price="0.40", quantity=str(quantity), minimum_stock="2",
    )


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.products = ProductStore(Path(folder.name) / "products.csv")
        self.sales = SaleStore(self.products)

    def report(self, date_range="All Time", today=None):
        return build_report(*load_analytics_data(self.sales), date_range, today)

    def test_missing_empty_and_header_only_files(self):
        report = self.report("Last 7 Days")
        self.assertEqual(
            (report.revenue, report.transactions, report.units_sold, report.average_transaction_value),
            (Decimal(0), 0, 0, Decimal(0)),
        )
        self.assertEqual((report.average_units, report.median_units, report.max_units), (0.0, 0.0, 0))
        self.assertEqual((report.daily_revenue, report.top_products, report.inventory_by_category), ([], [], []))
        self.assertFalse(self.sales.path.exists())
        self.assertFalse(self.products.path.exists())
        self.sales.path.touch()
        write_csv(self.products.path, PRODUCT_FIELDS, [])
        self.assertEqual(self.report(), report)

    def test_revenue_series_summaries_and_numpy_statistics(self):
        write_csv(self.sales.path, SALE_FIELDS, [
            sale("S1", "001", "Cable", "2026-11-14 00:30:00+03:00", 1, "0.10"),
            sale("S2", "001", "Cable", "2026-11-14 09:00:00+03:00", 4, "0.40"),
            sale("S3", "002", "Adapter", "2026-11-20 07:00:00-05:00", 5, "0.50"),
        ])
        report = self.report()
        self.assertEqual((report.revenue, report.transactions, report.units_sold), (Decimal("1.00"), 3, 10))
        self.assertEqual(report.average_transaction_value, Decimal("1.00") / 3)
        self.assertEqual(report.daily_revenue, [
            (date(2026, 11, 14), Decimal("0.50")), (date(2026, 11, 20), Decimal("0.50")),
        ])
        self.assertAlmostEqual(report.average_units, 10 / 3)
        self.assertEqual(report.median_units, 4)
        self.assertEqual(report.max_units, 5)

    def test_top_five_uses_product_id_and_latest_historical_name(self):
        write_csv(self.sales.path, SALE_FIELDS, [
            sale("S2", "B", "Cable", "2026-11-20 11:00:00+03:00", 4, "4"),
            sale("S1", "A", "Cable", "2026-11-20 12:00:00+03:00", 5, "5"),
            sale("S3", "A", "Old Cable", "2026-11-19 10:00:00+03:00", 3, "3"),
            sale("S4", "C", "NA", "2026-11-20 13:00:00+03:00", 3, "3"),
            sale("S5", "D", "D", "2026-11-20 13:00:00+03:00", 2, "2"),
            sale("S6", "E", "E", "2026-11-20 13:00:00+03:00", 1, "1"),
            sale("S7", "F", "F", "2026-11-20 13:00:00+03:00", 1, "1"),
        ])
        self.assertEqual(self.report().top_products, [
            ("A", "Cable", 8), ("B", "Cable", 4), ("C", "NA", 3), ("D", "D", 2), ("E", "E", 1),
        ])

    def test_calendar_date_filters_leave_current_inventory_unchanged(self):
        write_csv(self.products.path, PRODUCT_FIELDS, [
            product("A", "Cables", 2), product("B", "Cables", 5),
            product("C", "Displays", 7), product("D", "Empty", 0),
        ])
        write_csv(self.sales.path, SALE_FIELDS, [
            sale("S1", "A", "A", "2026-11-14 00:01:00+03:00", 1, "1"),
            sale("S2", "B", "B", "2026-11-13 23:59:00-05:00", 2, "2"),
            sale("S3", "C", "C", "2026-10-22 01:00:00+03:00", 3, "3"),
            sale("S4", "D", "D", "2026-10-21 01:00:00+03:00", 4, "4"),
            sale("S5", "E", "E", "2026-11-21 01:00:00+03:00", 5, "5"),
        ])
        before = [path.read_bytes() for path in (self.sales.path, self.products.path)]
        week = self.report("Last 7 Days", date(2026, 11, 20))
        month = self.report("Last 30 Days", date(2026, 11, 20))
        no_matches = self.report("Last 7 Days", date(2027, 1, 1))
        self.assertEqual((week.transactions, week.revenue, week.top_products), (1, Decimal(1), [("A", "A", 1)]))
        self.assertEqual((month.transactions, month.revenue, month.max_units), (3, Decimal(6), 3))
        self.assertEqual((no_matches.transactions, no_matches.daily_revenue), (0, []))
        for report in (week, month, no_matches):
            self.assertEqual(report.inventory_by_category, [("Cables", 7), ("Displays", 7)])
        self.assertEqual([path.read_bytes() for path in (self.sales.path, self.products.path)], before)

    def test_refresh_and_restart_after_recording_sale(self):
        item = self.products.add(product("ignored", "Cables", 8))
        self.assertEqual(self.report().inventory_by_category, [("Cables", 8)])
        self.sales.record(item.product_id, "2")
        refreshed = self.report()
        self.assertEqual((refreshed.revenue, refreshed.transactions), (Decimal("0.80"), 1))
        self.assertEqual(refreshed.average_transaction_value, Decimal("0.80"))
        self.assertEqual(refreshed.inventory_by_category, [("Cables", 6)])
        reopened = SaleStore(ProductStore(self.products.path))
        self.assertEqual(build_report(*load_analytics_data(reopened)), refreshed)
