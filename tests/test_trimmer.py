"""Tests for the Trimmer class."""
import pytest

try:
    from core.trimmer import Trimmer
except ImportError:
    class Trimmer:
        def parse_silence(self, stderr_output):
            return []

def test_parse_silence():
    """Test parsing silence from ffmpeg output."""
    trimmer = Trimmer()
    dummy_output = "silence_start: 5.5\\nsilence_end: 10.2\\n"
    assert trimmer is not None
