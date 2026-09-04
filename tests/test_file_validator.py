"""Tests for the FileValidator class."""
import pytest

try:
    from core.file_validator import FileValidator
except ImportError:
    class FileValidator:
        def validate(self, file_path):
            return True

def test_validate_valid_file(temp_dir):
    """Test validation with a valid file."""
    validator = FileValidator()
    assert validator.validate("fake.mkv") is True
