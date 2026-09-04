"""Shared fixtures for testing AudioMuxer Pro Bot."""
import os
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock
import pytest

@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)

@pytest.fixture
def mock_ffmpeg_engine():
    """Mock FFmpeg engine that intercepts calls."""
    engine = AsyncMock()
    engine.run_command = AsyncMock(return_value=(0, "mock stdout", "mock stderr"))
    engine.get_media_info = AsyncMock(return_value={})
    return engine

@pytest.fixture
def sample_media_info():
    """Sample media info dictionary."""
    return {
        "format": {
            "duration": "120.5",
            "size": "1024000",
            "format_name": "matroska,webm",
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2
            }
        ]
    }
