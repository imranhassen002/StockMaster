import unittest

from stockmaster.regex_validation import (
    validate_product_name,
    validate_category
)


class TestRegexValidation(unittest.TestCase):

    def test_valid_product_name(self):

        result = validate_product_name(
            "Samsung Galaxy S25"
        )

        self.assertEqual(
            result,
            "Samsung Galaxy S25"
        )

    def test_invalid_product_name(self):

        with self.assertRaises(ValueError):

            validate_product_name("@#$%")

    def test_empty_product_name(self):

        with self.assertRaises(ValueError):

            validate_product_name("")

    def test_product_name_too_long(self):

        with self.assertRaises(ValueError):

            validate_product_name("A" * 101)

    def test_valid_category(self):

        result = validate_category("Electronics")

        self.assertEqual(
            result,
            "Electronics"
        )

    def test_invalid_category(self):

        with self.assertRaises(ValueError):

            validate_category("123")

    def test_empty_category(self):

        with self.assertRaises(ValueError):

            validate_category("")

    def test_category_too_long(self):

        with self.assertRaises(ValueError):

            validate_category("A" * 51)


if __name__ == "__main__":
    unittest.main()
