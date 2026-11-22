from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Product:
    product_id: str
    name: str
    category: str
    unit_cost: Decimal
    selling_price: Decimal
    quantity: int
    minimum_stock: int

    @property
    def inventory_value(self):
        return self.unit_cost * self.quantity

    @property
    def stock_status(self):
        if self.quantity == 0:
            return "Out of Stock"
        if self.quantity <= self.minimum_stock:
            return "Low Stock"
        return "In Stock"


PRODUCT_FIELDS = [field.name for field in fields(Product)]
EDITABLE_FIELDS = (
    ("name", "Product Name"),
    ("category", "Category"),
    ("unit_cost", "Unit Cost"),
    ("selling_price", "Selling Price"),
    ("quantity", "Quantity"),
    ("minimum_stock", "Minimum Stock"),
)


def validate_product(product_id, values):
    """Convert form or CSV text to a validated product."""
    name = values["name"].strip()
    category = values["category"].strip()
    if not name:
        raise ValueError("Product Name is required.")
    if not category:
        raise ValueError("Category is required.")

    return Product(
        product_id, name, category,
        parse_price(values["unit_cost"], "Unit Cost"),
        parse_price(values["selling_price"], "Selling Price"),
        parse_stock_count(values["quantity"], "Quantity"),
        parse_stock_count(values["minimum_stock"], "Minimum Stock"),
    )


def parse_price(value, label):
    message = f"{label} must be a finite number of zero or greater."
    try:
        price = Decimal(value.strip())
    except InvalidOperation as error:
        raise ValueError(message) from error
    if not price.is_finite() or price < 0:
        raise ValueError(message)
    return price.copy_abs()


def parse_stock_count(value, label):
    value = value.strip()
    try:
        if value.isdecimal():
            return int(value)
    except ValueError:
        pass
    raise ValueError(f"{label} must be a non-negative whole number.")


def search_products(products, query):
    query = query.strip().casefold()
    return [
        product for product in products
        if any(query in value.casefold()
               for value in (product.name, product.category, product.product_id))
    ]


def inventory_summary(products):
    inventory_value = sum(
        (product.inventory_value for product in products), Decimal(0)
    )
    low_stock_count = sum(product.quantity <= product.minimum_stock for product in products)
    return len(products), inventory_value, low_stock_count
