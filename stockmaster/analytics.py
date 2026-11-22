from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from stockmaster.products import PRODUCT_FIELDS, parse_price, parse_stock_count
from stockmaster.sales import SALE_FIELDS, parse_sale_quantity


DATE_RANGES = {"All Time": None, "Last 7 Days": 7, "Last 30 Days": 30}


@dataclass(frozen=True)
class AnalyticsReport:
    revenue: Decimal
    transactions: int
    units_sold: int
    average_transaction_value: Decimal
    daily_revenue: list
    top_products: list
    inventory_by_category: list
    average_units: float
    median_units: float
    max_units: int


def read_dataset(path, fields):
    """Load CSV text without converting IDs to numbers or money to floats."""
    try:
        data = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=fields)
    if not set(fields).issubset(data.columns):
        raise ValueError(f"{path.name} is missing required columns.")
    return data


def load_analytics_data(sale_store):
    # Share the sales transaction lock so both files describe the same snapshot.
    with sale_store.products.locked():
        sales = read_dataset(sale_store.path, SALE_FIELDS)
        products = read_dataset(sale_store.products.path, PRODUCT_FIELDS)
    return sales, products


def build_report(sales, products, date_range="All Time", today=None):
    """Build summary values and chart series from the CSV snapshot."""
    days = DATE_RANGES[date_range]
    sales = sales.copy()
    timestamps = sales["timestamp"].map(datetime.fromisoformat)
    # Keep each sale on the calendar date recorded in its original timestamp.
    sales["sale_date"] = timestamps.map(lambda timestamp: timestamp.date())
    if days is not None and not sales.empty:
        today = date.today() if today is None else today
        start = today - timedelta(days=days - 1)
        sales = sales.loc[sales["sale_date"].between(start, today)].copy()
    sales["total_amount"] = sales["total_amount"].map(
        lambda amount: parse_price(amount, "Total amount")
    )
    sales["quantity"] = sales["quantity"].map(parse_sale_quantity).astype(object)

    revenue, transactions, units_sold, average_value = sales_totals(sales)
    units = sales["quantity"].to_numpy(dtype=object)
    average_units = median_units = 0.0
    max_units = 0
    daily_revenue = []
    top_products = []
    if transactions:
        average_units = float(np.mean(units))
        median_units = float(np.median(units.astype(float)))
        max_units = int(np.max(units))
        daily_revenue = list(sales.groupby("sale_date")["total_amount"].sum().items())
        top_products = rank_products(sales, timestamps)

    inventory = products.assign(quantity=products["quantity"].map(
        lambda quantity: parse_stock_count(quantity, "Quantity")
    ).astype(object))
    by_category = inventory.groupby("category")["quantity"].sum()
    inventory_by_category = [(category, quantity) for category, quantity in by_category.items()
                             if quantity > 0]

    return AnalyticsReport(
        revenue=revenue,
        transactions=transactions,
        units_sold=units_sold,
        average_transaction_value=average_value,
        daily_revenue=daily_revenue,
        top_products=top_products,
        inventory_by_category=inventory_by_category,
        average_units=average_units,
        median_units=median_units,
        max_units=max_units,
    )


def sales_totals(sales):
    revenue = sum(sales["total_amount"], Decimal(0))
    transactions = len(sales)
    units_sold = sum(sales["quantity"])
    average = revenue / transactions if transactions else Decimal(0)
    return revenue, transactions, units_sold, average


def latest_product_names(sales, timestamps):
    dated = sales.assign(sort_time=pd.to_datetime(timestamps.loc[sales.index], utc=True))
    latest = dated.sort_values("sort_time", kind="stable").drop_duplicates("product_id", keep="last")
    return latest.set_index("product_id")["product_name"]


def rank_products(sales, timestamps):
    names = latest_product_names(sales, timestamps)
    ranking = sales.groupby("product_id", as_index=False)["quantity"].sum()
    ranking = ranking.sort_values(["quantity", "product_id"], ascending=[False, True]).head(5)
    return [(product_id, names[product_id], quantity)
            for product_id, quantity in ranking.itertuples(index=False, name=None)]
