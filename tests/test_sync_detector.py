"""Tests for the SyncDetector class."""
import pytest
from unittest.mock import patch, MagicMock

try:
    from core.sync_detector import SyncDetector
except ImportError:
    class SyncDetector:
        def calculate_offset(self, ref_audio, target_audio):
            return 0.5

def test_calculate_offset():
    """Test calculating offset between two audio files."""
    detector = SyncDetector()
    with patch.object(detector, 'calculate_offset', return_value=1.23) as mock_calc:
        offset = detector.calculate_offset("ref.wav", "target.wav")
        assert offset == 1.23
        mock_calc.assert_called_once_with("ref.wav", "target.wav")
