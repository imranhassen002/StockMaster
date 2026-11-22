import csv
import json
import os
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

from stockmaster.csv_storage import write_csv
from stockmaster.products import PRODUCT_FIELDS, validate_product
from stockmaster.sales import read_sales


PRODUCTS_PATH = Path(__file__).resolve().parents[1] / "data" / "products.csv"


class ProductStore:
    """Read and update product records in a project-relative CSV file."""

    def __init__(self, path=PRODUCTS_PATH):
        self.path = Path(path)
        self.sales_path = self.path.with_name("sales.csv")
        self.sale_journal = self.path.with_name("pending_sale.json")

    def load(self):
        with self.locked():
            return self._load()

    def _load(self):
        try:
            with self.path.open("x", encoding="utf-8", newline="") as file:
                csv.writer(file).writerow(PRODUCT_FIELDS)
        except FileExistsError:
            pass

        with self.path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, strict=True)
            if reader.fieldnames is None:
                return []
            if sorted(reader.fieldnames) != sorted(PRODUCT_FIELDS):
                raise ValueError("The products CSV has an invalid header.")

            products = []
            product_ids = set()
            for row in reader:
                try:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError("Unexpected number of fields.")
                    product_id = row["product_id"].strip()
                    if not product_id or product_id in product_ids:
                        raise ValueError("Missing or duplicate Product ID.")
                    products.append(validate_product(product_id, row))
                    product_ids.add(product_id)
                except ValueError as error:
                    raise ValueError(f"Products CSV, line {reader.line_num}: {error}") from error
            return products

    def add(self, values):
        with self.locked():
            products = self._load()
            existing_ids = {product.product_id.casefold() for product in products}
            product_id = self._new_id(existing_ids)
            product = validate_product(product_id, values)
            self._save([*products, product])
        return product

    def import_products(self, candidates):
        """Append a reviewed batch with one atomic CSV update."""
        if not candidates:
            return []
        with self.locked():
            products = self._load()
            reserved_ids = {product.product_id.casefold() for product in products}
            for candidate in candidates:
                if candidate.product_id:
                    key = candidate.product_id.casefold()
                    if key in reserved_ids:
                        raise ValueError(
                            f"Product ID {candidate.product_id} is already in use. Review the import again."
                        )
                    reserved_ids.add(key)

            imported = []
            for candidate in candidates:
                product_id = candidate.product_id or self._new_id(reserved_ids)
                reserved_ids.add(product_id.casefold())
                imported.append(replace(candidate, product_id=product_id))
            self._save([*products, *imported])
            return imported

    @staticmethod
    def _new_id(reserved_ids):
        product_id = uuid4().hex[:12].upper()
        while product_id.casefold() in reserved_ids:
            product_id = uuid4().hex[:12].upper()
        return product_id

    def edit(self, product_id, values, expected_product=None):
        with self.locked():
            products = self._load()
            index = self._find_index(products, product_id)
            if expected_product is not None and products[index] != expected_product:
                raise ValueError("This product changed. Close the form, refresh the table, and try again.")
            product = validate_product(product_id, values)
            products[index] = product
            self._save(products)
        return product

    def delete(self, product_id):
        with self.locked():
            products = self._load()
            del products[self._find_index(products, product_id)]
            self._save(products)

    @contextmanager
    def locked(self):
        """Serialize access across app instances and recover interrupted sales."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Lock a separate file because saving replaces the CSV itself.
        lock_path = self.path.with_suffix(".lock")
        with lock_path.open("a+b") as lock:
            lock.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            # Closing the handle releases the lock, even if saving fails.
            self.recover_sale()
            yield

    def recover_sale(self):
        """Restore consistent stock and return whether the pending sale was committed."""
        try:
            with self.sale_journal.open(encoding="utf-8") as file:
                pending = json.load(file)
        except FileNotFoundError:
            return
        try:
            sale_id = pending["sale_id"]
            product_id = pending["product_id"]
            old_quantity = pending["old_quantity"]
            new_quantity = pending["new_quantity"]
            if (not isinstance(sale_id, str) or not sale_id or
                    not isinstance(product_id, str) or not product_id or
                    type(old_quantity) is not int or type(new_quantity) is not int or
                    not 0 <= new_quantity < old_quantity):
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("The pending sale recovery file is invalid.") from error

        # An atomic sales.csv replacement is the commit point for the sale.
        committed = any(sale.sale_id == sale_id for sale in read_sales(self.sales_path))
        products = self._load()
        index = self._find_index(products, product_id)
        product = products[index]
        if product.quantity not in (old_quantity, new_quantity):
            raise ValueError("Product stock changed while a sale was pending recovery.")
        expected = new_quantity if committed else old_quantity
        if product.quantity != expected:
            products[index] = replace(product, quantity=expected)
            self._save(products)
        self.sale_journal.unlink()
        return committed

    @staticmethod
    def _find_index(products, product_id):
        for index, product in enumerate(products):
            if product.product_id == product_id:
                return index
        raise ValueError("This product no longer exists. Refresh the product table.")

    def _save(self, products):
        write_csv(self.path, PRODUCT_FIELDS, (asdict(product) for product in products))
