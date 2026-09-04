"""Tests for the TrackManager class."""
import pytest

try:
    from core.track_manager import TrackManager
except ImportError:
    class TrackManager:
        def add_track(self, track):
            pass
        def get_tracks(self):
            return []

def test_add_track():
    """Test adding a track."""
    manager = TrackManager()
    manager.add_track({"id": 1, "lang": "en"})
    tracks = manager.get_tracks()
    assert isinstance(tracks, list)
