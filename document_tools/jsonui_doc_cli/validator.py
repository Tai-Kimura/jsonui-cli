"""Re-export TestValidator from the single in-repo test validator.

The test-definition validator + schema constants live in one place only:
the ``jsonui_test_cli`` package (jsonui-cli/test_tools). ``jsonui-doc`` imports
them from there instead of carrying its own copy, so there is exactly one
generation of the validator in this repo (plan D3). Both packages are installed
editable by install.sh (test_tools before document_tools).
"""
from jsonui_test_cli.validation import TestValidator, ValidationResult

__all__ = ["TestValidator", "ValidationResult"]
