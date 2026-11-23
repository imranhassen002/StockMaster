import os
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from math import isfinite
from pathlib import Path
from sys import float_info
from tempfile import NamedTemporaryFile

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import IllegalCharacterError

from stockmaster.analytics import latest_product_names, sales_totals
from stockmaster.products import EDITABLE_FIELDS, inventory_summary, validate_product
from stockmaster.regex_validation import validate_product_name, validate_category
from stockmaster.sales import SALE_FIELDS


PRODUCT_COLUMNS = ("Product ID", *(label for _, label in EDITABLE_FIELDS), "Stock Status")
SALES_COLUMNS = (
    "Sale ID", "Date and Time", "Product ID", "Product Name",
    "Quantity Sold", "Unit Price", "Total Amount",
)
MONEY_FORMAT = "#,##0.00;(#,##0.00)"
MONEY_COLUMNS = {
    "Unit Cost", "Selling Price", "Unit Price", "Total Amount", "Total Revenue", "Inventory Value",
}


@dataclass
class ImportPreview:
    valid: list
    invalid: list
    duplicates: list


def review_product_import(path, existing_products):
    """Read the first worksheet and classify each nonblank product row."""
    if Path(path).suffix.lower() != ".xlsx":
        raise ImportFormatError("Choose an .xlsx workbook.")
    try:
        with pd.ExcelFile(path, engine="openpyxl", engine_kwargs={"data_only": False}) as workbook:
            frame = workbook.parse(0, header=None, dtype=object, keep_default_na=False)
            worksheet = workbook.book.worksheets[0]
            columns = import_columns(frame)
            bad_cells = set()
            for row_number, row in enumerate(worksheet.iter_rows(), start=1):
                if any(index < len(row) and row[index].data_type in ("f", "e")
                       for index in columns.values()):
                    bad_cells.add(row_number)
    except OSError:
        raise
    except ImportFormatError:
        raise
    except Exception as error:
        raise ImportFormatError("Unable to read this workbook. Choose a valid .xlsx file.") from error

    ids = {product.product_id.casefold() for product in existing_products}
    preview = ImportPreview([], [], [])
    for row_number, row in enumerate(frame.iloc[1:].itertuples(index=False, name=None), start=2):
        values = {field: cell_text(row[index]) for field, index in columns.items()}
        if row_number in bad_cells:
            preview.invalid.append((row_number, "Use literal values in product fields. Formula or error cell found."))
            continue
        if not any(values.values()):
            continue
        product_id = values.get("product_id", "")
        try:
            # Regex check on the name and category read from this Excel row.
            # A ValueError marks only this row as invalid in the review window.
            if values["name"]:
                try:
                    values["name"] = validate_product_name(values["name"])
                    values["category"] = validate_category(values["category"])
                except ValueError as error:
                    raise ValueError(f"Invalid Excel product data: {error}") from error
            product = validate_product(product_id, values)
        except ValueError as error:
            preview.invalid.append((row_number, str(error)))
            continue
        key = product_id.casefold()
        if key and key in ids:
            preview.duplicates.append((row_number, f"Product ID {product_id} is already in use."))
            continue
        if key:
            ids.add(key)
        preview.valid.append(product)
    return preview


class ImportFormatError(ValueError):
    """The workbook cannot be used as a product import."""


def import_columns(frame):
    expected = {"product id": "product_id", **{
        label.casefold(): field for field, label in EDITABLE_FIELDS
    }}
    columns = {}
    if not frame.empty:
        for index, header in enumerate(frame.iloc[0]):
            field = expected.get(cell_text(header).casefold())
            if field is None:
                continue
            if field in columns:
                raise ImportFormatError(f"Duplicate column header: {header}.")
            columns[field] = index
    if missing := [label for field, label in EDITABLE_FIELDS if field not in columns]:
        raise ImportFormatError(f"Missing required columns: {', '.join(missing)}.")
    return columns


def cell_text(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def product_frame(products):
    return pd.DataFrame(
        [(product.product_id, product.name, product.category, product.unit_cost,
          product.selling_price, product.quantity, product.minimum_stock, product.stock_status)
         for product in products],
        columns=PRODUCT_COLUMNS,
        dtype=object,
    )


def sales_frame(sales):
    return pd.DataFrame(
        [(sale.sale_id, sale.timestamp.isoformat(sep=" "),
          sale.product_id, sale.product_name, sale.quantity, sale.unit_price, sale.total_amount)
         for sale in sales],
        columns=SALES_COLUMNS,
        dtype=object,
    )


def export_products(path, products):
    save_workbook(path, {"Inventory": product_frame(products)})


def export_sales(path, sales):
    save_workbook(path, {"Sales History": sales_frame(sales)})


def generate_report(path, products, sales):
    sale_data = pd.DataFrame([asdict(sale) for sale in sales], columns=SALE_FIELDS, dtype=object)
    revenue, transactions, units, average = sales_totals(sale_data)
    product_count, inventory_value, low_stock = inventory_summary(products)
    summary = pd.DataFrame([
        ("Total Products", product_count),
        ("Current Inventory Value", inventory_value),
        ("Total Sales Revenue", revenue),
        ("Total Transactions", transactions),
        ("Total Units Sold", units),
        ("Average Transaction Value", average),
        ("Low / Out of Stock Products", low_stock),
    ], columns=["Metric", "Value"], dtype=object)

    performance = sale_data.groupby("product_id", as_index=False).agg(
        quantity=("quantity", "sum"), revenue=("total_amount", "sum"),
    )
    names = latest_product_names(sale_data, sale_data["timestamp"])
    performance.insert(1, "product_name", performance["product_id"].map(names))
    performance = performance.sort_values(["quantity", "product_id"], ascending=[False, True])
    performance.columns = ["Product ID", "Product Name", "Total Units Sold", "Total Revenue"]

    categories = pd.DataFrame(
        [(product.category, product.quantity, product.inventory_value) for product in products],
        columns=["Product Category", "Total Available Quantity", "Inventory Value"], dtype=object,
    )
    categories = categories.groupby("Product Category", as_index=False).sum()

    save_workbook(path, {
        "Business Summary": summary,
        "Inventory": product_frame(products),
        "Sales History": sales_frame(sales),
        "Product Performance": performance,
        "Category Summary": categories,
    }, generated_at=datetime.now().astimezone())


def save_workbook(path, sheets, generated_at=None):
    """Write a complete workbook before replacing the chosen destination."""
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Choose a destination with an .xlsx extension.")
    # Excel needs numeric cells for currency formats and calculations.
    prepared = {name: frame.apply(lambda column: column.map(excel_value))
                for name, frame in sheets.items()}
    temp_path = None
    try:
        with NamedTemporaryFile(dir=path.parent, suffix=".xlsx", delete=False) as file:
            temp_path = Path(file.name)
        with pd.ExcelWriter(temp_path, engine="openpyxl") as writer:
            for name, frame in prepared.items():
                summary = name == "Business Summary"
                header_row = 4 if summary else 1
                frame.to_excel(writer, sheet_name=name, index=False, startrow=header_row - 1)
                sheet = writer.sheets[name]
                format_sheet(sheet, header_row)
                if summary:
                    sheet["A1"] = "StockMaster Business Report"
                    sheet["A1"].font = Font(bold=True, size=16, color="14233D")
                    sheet["A2"] = f"Generated: {generated_at.isoformat(sep=' ', timespec='seconds')}"
                    sheet["A3"] = "Scope: All-time sales and current inventory"
                    for row in (1, 2, 3):
                        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
                    sheet.column_dimensions["A"].width = 34
                    sheet.column_dimensions["B"].width = 28
                    for row in (6, 7, 10):
                        sheet.cell(row=row, column=2).number_format = MONEY_FORMAT
        with temp_path.open("r+b") as file:
            os.fsync(file.fileno())
        temp_path.replace(path)
    except IllegalCharacterError as error:
        raise ValueError("Some text contains characters that Excel cannot store.") from error
    except (OSError, ValueError):
        raise
    except Exception as error:
        raise ValueError("Excel could not store this workbook.") from error
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def excel_value(value):
    if isinstance(value, Decimal):
        number = float(value)
        if not isfinite(number):
            raise ValueError("A monetary value is too large for Excel.")
        if value != 0 and abs(number) < float_info.min:
            raise ValueError("A nonzero monetary value is too small for Excel.")
        return number
    if isinstance(value, str) and len(value) > 32767:
        raise ValueError("A text value exceeds Excel's cell length limit.")
    return value


def format_sheet(sheet, header_row):
    sheet.freeze_panes = f"A{header_row + 1}"
    last_column = get_column_letter(sheet.max_column)
    sheet.auto_filter.ref = f"A{header_row}:{last_column}{sheet.max_row}"
    sheet.row_dimensions[header_row].height = 24
    border = Border(bottom=Side(style="hair", color="DCE4EF"))
    for column in sheet.iter_cols(min_row=header_row):
        header, *cells = column
        header.font = Font(bold=True, color="FFFFFF")
        header.fill = PatternFill("solid", fgColor="14233D")
        header.alignment = Alignment(vertical="center")
        money = header.value in MONEY_COLUMNS
        width = len(header.value) + 5
        for cell in cells:
            if isinstance(cell.value, str):
                # openpyxl infers formulas from strings beginning with "=".
                cell.data_type = "s"
            cell.border = border
            if money:
                cell.number_format = MONEY_FORMAT
                width = max(width, len(f"{cell.value:,.2f}") + 3)
            elif cell.value is not None:
                width = max(width, len(str(cell.value)) + 3)
                if isinstance(cell.value, str) and len(cell.value) > 45:
                    cell.alignment = Alignment(wrap_text=True)
        sheet.column_dimensions[header.column_letter].width = min(max(width, 13), 48)
