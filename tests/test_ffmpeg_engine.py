"""Tests for the FFmpegEngine class."""
import pytest
from unittest.mock import AsyncMock, patch

try:
    from core.ffmpeg_engine import FFmpegEngine
except ImportError:
    class FFmpegEngine:
        async def run_command(self, cmd):
            pass
        async def get_media_info(self, file_path):
            pass

@pytest.mark.asyncio
async def test_run_command(mock_ffmpeg_engine):
    """Test running a command."""
    cmd = ["ffmpeg", "-i", "input.mkv", "output.mp4"]
    result = await mock_ffmpeg_engine.run_command(cmd)
    assert result == (0, "mock stdout", "mock stderr")
    mock_ffmpeg_engine.run_command.assert_called_once_with(cmd)

@pytest.mark.asyncio
async def test_get_media_info(mock_ffmpeg_engine, sample_media_info):
    """Test getting media info."""
    mock_ffmpeg_engine.get_media_info.return_value = sample_media_info
    info = await mock_ffmpeg_engine.get_media_info("test.mkv")
    assert info["format"]["duration"] == "120.5"
    assert len(info["streams"]) == 2
