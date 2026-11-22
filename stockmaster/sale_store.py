import csv
import json
from dataclasses import asdict, replace
from datetime import datetime
from uuid import uuid4

from stockmaster.csv_storage import atomic_text_write, write_csv
from stockmaster.sales import SALE_FIELDS, Sale, parse_sale_quantity, read_sales


class SaleStore:
    """Record sales and adjust inventory under the shared product lock."""

    def __init__(self, product_store):
        self.products = product_store
        self.path = product_store.sales_path

    def load(self):
        with self.products.locked():
            return self._load()

    def load_dashboard_data(self):
        with self.products.locked():
            return self.products._load(), self._load()

    def _load(self):
        if not self.path.exists():
            write_csv(self.path, SALE_FIELDS, ())
        return read_sales(self.path)

    def record(self, product_id, quantity_text, expected_price=None):
        if not product_id:
            raise ValueError("Select a product first.")
        quantity = parse_sale_quantity(quantity_text)
        with self.products.locked():
            products = self.products._load()
            index = self.products._find_index(products, product_id)
            product = products[index]
            if product.quantity == 0:
                raise ValueError("This product is out of stock.")
            if quantity > product.quantity:
                raise ValueError(f"Only {product.quantity} units are currently available.")
            if expected_price is not None and product.selling_price != expected_price:
                raise ValueError("The selling price changed. Review the updated price and try again.")

            sales = self._load()
            existing_ids = {sale.sale_id for sale in sales}
            sale_id = uuid4().hex[:12].upper()
            while sale_id in existing_ids:
                sale_id = uuid4().hex[:12].upper()
            sale = Sale(
                sale_id, datetime.now().astimezone().replace(microsecond=0),
                product_id, product.name, quantity, product.selling_price,
                product.selling_price * quantity,
            )
            remaining = product.quantity - quantity
            products[index] = replace(product, quantity=remaining)
            with atomic_text_write(self.products.sale_journal) as file:
                json.dump({
                    "sale_id": sale_id, "product_id": product_id,
                    "old_quantity": product.quantity, "new_quantity": remaining,
                }, file)

            try:
                self.products._save(products)
                self._save([*sales, sale])
            except (OSError, ValueError, csv.Error):
                try:
                    committed = self.products.recover_sale()
                except (OSError, ValueError, csv.Error) as recovery_error:
                    raise OSError(
                        f"Sale {sale_id} could not be finalized. Recovery is pending. "
                        f"Check Sales History after storage is available. {recovery_error}"
                    ) from recovery_error
                if committed:
                    return sale
                raise

            try:
                self.products.sale_journal.unlink()
            except OSError:
                # Both CSVs are committed. The next access retries journal cleanup.
                pass
            return sale

    def _save(self, sales):
        write_csv(self.path, SALE_FIELDS, (asdict(sale) for sale in sales))
