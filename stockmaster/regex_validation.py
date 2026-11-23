import re

# Product name: letters, numbers, spaces and common symbols
PRODUCT_NAME_PATTERN = re.compile(
    r"[^\W_][\w .,'’&()/%+#\-]*",
    re.UNICODE
)

# Category: starts with a letter
CATEGORY_PATTERN = re.compile(
    r"[^\W\d_][\w .,'’&()/+\-]*",
    re.UNICODE
)


def validate_product_name(name):
    """Validate a product name using regular expressions."""

    if not isinstance(name, str):
        raise ValueError("Product name must be text.")

    name = name.strip()

    if not 2 <= len(name) <= 100:
        raise ValueError(
            "Product name must contain 2 to 100 characters."
        )

    if not PRODUCT_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "Product name contains invalid characters."
        )

    return name


def validate_category(category):
    """Validate a product category using regular expressions."""

    if not isinstance(category, str):
        raise ValueError("Category must be text.")

    category = category.strip()

    if not 2 <= len(category) <= 50:
        raise ValueError(
            "Category must contain 2 to 50 characters."
        )

    if not CATEGORY_PATTERN.fullmatch(category):
        raise ValueError(
            "Category contains invalid characters."
        )

    return category
