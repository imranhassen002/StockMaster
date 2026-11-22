import csv
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal

from stockmaster.products import parse_price, parse_stock_count


@dataclass(frozen=True)
class Sale:
    sale_id: str
    timestamp: datetime
    product_id: str
    product_name: str
    quantity: int
    unit_price: Decimal
    total_amount: Decimal


SALE_FIELDS = [field.name for field in fields(Sale)]


def parse_sale_quantity(text):
    message = "Quantity to sell must be a positive whole number."
    try:
        quantity = parse_stock_count(text, "Quantity to sell")
    except ValueError as error:
        raise ValueError(message) from error
    if quantity == 0:
        raise ValueError(message)
    return quantity


def total_revenue(sales):
    return sum((sale.total_amount for sale in sales), Decimal(0))


def filter_sales(sales, query, sale_date=None):
    query = query.strip().casefold()
    return [
        sale for sale in sales
        if (sale_date is None or sale.timestamp.date() == sale_date)
        and any(query in value.casefold()
                for value in (sale.product_name, sale.product_id, sale.sale_id))
    ]


def read_sales(path):
    """Read historical snapshots and reject malformed records before writing."""
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, strict=True)
        if reader.fieldnames is None:
            return []
        if sorted(reader.fieldnames) != sorted(SALE_FIELDS):
            raise ValueError("The sales CSV has an invalid header.")

        sales = []
        ids = set()
        for row in reader:
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Unexpected number of fields.")
                if not row["sale_id"] or row["sale_id"] in ids:
                    raise ValueError("Missing or duplicate Sale ID.")
                if not row["product_id"] or not row["product_name"]:
                    raise ValueError("Missing product details.")
                sales.append(Sale(
                    row["sale_id"], datetime.fromisoformat(row["timestamp"]),
                    row["product_id"], row["product_name"],
                    parse_sale_quantity(row["quantity"]),
                    parse_price(row["unit_price"], "Unit price"),
                    parse_price(row["total_amount"], "Total amount"),
                ))
                ids.add(row["sale_id"])
            except ValueError as error:
                raise ValueError(f"Sales CSV, line {reader.line_num}: {error}") from error
        return sales
