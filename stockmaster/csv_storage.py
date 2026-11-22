import csv
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile


@contextmanager
def atomic_text_write(path):
    """Replace a file only after its replacement has been fully written."""
    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False
        ) as file:
            temporary_path = Path(file.name)
            yield file
            file.flush()
            os.fsync(file.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_csv(path, fieldnames, rows):
    with atomic_text_write(path) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        field_limit = csv.field_size_limit()
        for row in rows:
            for field, value in row.items():
                if len(str(value)) > field_limit:
                    label = field.replace("_", " ").capitalize()
                    raise ValueError(f"{label} exceeds the CSV limit of {field_limit:,} characters.")
            writer.writerow(row)
