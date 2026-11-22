# StockMaster – Smart Inventory & Sales Analytics System

A Python desktop application for small businesses to manage products, record sales and analyse business performance. Built with Tkinter as the final project for the Visual Programming course at Haliç University.

## Features

- **Dashboard** – total products, inventory value, sales revenue and low / out-of-stock count
- **Products** – add, edit, delete and search products; colour-coded stock status (In Stock, Low Stock, Out of Stock)
- **Sales** – record sales with stock checks, automatic inventory updates, searchable sales history with date filter
- **Analytics** – revenue, transactions and units sold; revenue-over-time, top 5 products and inventory-by-category charts (Matplotlib embedded in Tkinter); date range filter
- **Excel** – import products, export inventory and sales, generate a 5-sheet business report
- **Storage** – CSV files with safe (atomic) writes and recovery of interrupted sales

## Technologies

Python · Tkinter / ttk · pandas · NumPy · Matplotlib · OpenPyXL · csv · Decimal · dataclasses · unittest

## Getting started

Requires Python 3.10+ with Tkinter.

```bash
python -m pip install -r requirements.txt
python main.py
```

On Windows you can also double-click **`Run StockMaster.bat`**.

The `data/` folder includes sample data (15 products, 48 sales).

## Running the tests

```bash
python -m unittest discover -s tests -v
```

42 automated tests cover products, sales, analytics, Excel features and the GUI.

## Project structure

```text
StockMaster/
├── main.py                  # Entry point
├── requirements.txt
├── data/                    # products.csv, sales.csv
├── stockmaster/
│   ├── app.py               # Main window and navigation
│   ├── styles.py            # Theme
│   ├── products.py          # Product model and validation
│   ├── sales.py             # Sale model and helpers
│   ├── product_store.py     # Product CSV storage and locking
│   ├── sale_store.py        # Sale recording and recovery
│   ├── csv_storage.py       # Atomic CSV writes
│   ├── analytics.py         # pandas / NumPy statistics
│   ├── excel_service.py     # OpenPyXL import / export / report
│   └── pages/               # Dashboard, Products, Sales, Analytics pages
└── tests/                   # unittest suite
```

## Authors

- Imran Khalid Hassen
- Aliyu Mohammed Daura

Developed with assistance from AI tools (OpenAI Codex, Claude); all AI usage is documented in the course submission.
