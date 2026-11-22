import csv
import tkinter as tk
from decimal import DecimalException
from tkinter import filedialog, messagebox, ttk


EXCEL_TYPES = [("Excel workbooks", "*.xlsx")]
EXCEL_ERRORS = (OSError, ValueError, csv.Error, DecimalException)


def show_excel_error(parent, title, error):
    message = str(error)
    if isinstance(error, PermissionError) or getattr(error, "winerror", None) in (32, 33):
        message = "Close the workbook in Excel and check that you have permission to access the file."
    messagebox.showerror(title, message, parent=parent)


def save_excel(parent, filename, write_workbook):
    path = filedialog.asksaveasfilename(
        parent=parent, initialfile=filename, defaultextension=".xlsx", filetypes=EXCEL_TYPES,
    )
    if not path:
        return
    try:
        write_workbook(path)
    except EXCEL_ERRORS as error:
        show_excel_error(parent, "Unable to save workbook", error)
        return
    messagebox.showinfo("Workbook saved", f"Saved to:\n{path}", parent=parent)


class ProductImportReview(tk.Toplevel):
    """Show the reviewed batch and save it only after explicit confirmation."""

    def __init__(self, page, preview):
        super().__init__(page)
        self.page = page
        self.preview = preview
        self.title("Review Product Import")
        self.transient(page.winfo_toplevel())

        content = ttk.Frame(self, padding=20)
        content.pack(fill="both", expand=True)
        ttk.Label(content, style="SectionTitle.TLabel", text="Review product import").pack(anchor="w")
        ttk.Label(content, text=(
            f"Valid products: {len(preview.valid)}    "
            f"Invalid products: {len(preview.invalid)}    "
            f"Duplicate products: {len(preview.duplicates)}"
        )).pack(anchor="w", pady=(8, 4))
        ttk.Label(content, text="Only valid new products will be added.").pack(anchor="w", pady=(0, 8))

        details = ttk.Frame(content)
        details.pack(fill="both", expand=True)
        issues = tk.Text(details, height=11, width=62, wrap="word", padx=8, pady=6)
        scrollbar = ttk.Scrollbar(details, orient="vertical", command=issues.yview)
        issues.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        issues.pack(side="left", fill="both", expand=True)
        for label, rows in (("Invalid", preview.invalid), ("Duplicate", preview.duplicates)):
            for row, reason in rows:
                issues.insert("end", f"Row {row} ({label}): {reason}\n")
        if not preview.invalid and not preview.duplicates:
            issues.insert("end", "No invalid or duplicate rows found.")
        issues.configure(state="disabled")

        actions = ttk.Frame(content)
        actions.pack(anchor="e", pady=(12, 0))
        cancel = ttk.Button(actions, text="Cancel", command=self.destroy)
        cancel.pack(side="left", padx=(0, 8))
        confirm = ttk.Button(actions, text="Import Valid Products", style="Primary.TButton",
                             command=self.confirm)
        confirm.pack(side="left")
        if not preview.valid:
            confirm.state(["disabled"])
        self.bind("<Escape>", lambda _event: self.destroy())
        self.wait_visibility()
        self.grab_set()
        cancel.focus_set()

    def confirm(self):
        try:
            imported = self.page.store.import_products(self.preview.valid)
        except EXCEL_ERRORS as error:
            show_excel_error(self, "Unable to import products", error)
            return
        self.destroy()
        self.page.refresh()
        messagebox.showinfo("Import complete", f"Added {len(imported)} product(s).", parent=self.page)
