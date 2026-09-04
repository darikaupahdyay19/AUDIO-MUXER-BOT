import hashlib
import math
import os
import re
import uuid
from pathlib import Path


def format_duration(seconds: float) -> str:
    """Convert seconds to 'HH:MM:SS' or 'MM:SS' for <1hr."""
    if seconds < 0:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human-readable size."""
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


def generate_job_id() -> str:
    """Generate UUID4 string."""
    return str(uuid.uuid4())


def parse_timestamp(timestamp_str: str) -> float:
    """Parse 'HH:MM:SS', 'HH:MM:SS.ms', 'MM:SS', or raw seconds to float seconds."""
    timestamp_str = timestamp_str.strip()
    try:
        # Check if it's just raw seconds
        return float(timestamp_str)
    except ValueError:
        pass

    # Match HH:MM:SS.ms, HH:MM:SS, MM:SS
    parts = timestamp_str.split(':')
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        else:
            raise ValueError(f"Invalid timestamp format: {timestamp_str}")
    except ValueError as e:
        raise ValueError(f"Invalid timestamp format: {timestamp_str}") from e


def sanitize_filename(name: str) -> str:
    """Remove/replace unsafe characters, limit length to 200 chars."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name[:200]


def get_file_hash(file_path: str) -> str:
    """SHA256 hash of file (read in 64KB chunks for memory efficiency)."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_file_extension(file_path: str) -> str:
    """Return lowercase extension including dot."""
    _, ext = os.path.splitext(file_path)
    return ext.lower()


def is_video_file(file_path: str) -> bool:
    """Check extension against VIDEO_FORMATS from bot.config."""
    from bot.config import VIDEO_FORMATS
    ext = get_file_extension(file_path)
    return ext in VIDEO_FORMATS


def is_audio_file(file_path: str) -> bool:
    """Check extension against AUDIO_FORMATS from bot.config."""
    from bot.config import AUDIO_FORMATS
    ext = get_file_extension(file_path)
    return ext in AUDIO_FORMATS


def generate_output_path(input_path: str, suffix: str, output_dir: str | None = None) -> str:
    """Generate output file path with suffix."""
    path = Path(input_path)
    new_name = f"{path.stem}_{suffix}{path.suffix}"
    if output_dir:
        return str(Path(output_dir) / new_name)
    return str(path.with_name(new_name))


def format_progress_bar(progress: float, length: int = 10) -> str:
    """Generate text progress bar like '[████░░░░░░] 40%'."""
    progress = max(0.0, min(100.0, progress))
    filled_len = int(length * progress // 100)
    bar = '█' * filled_len + '░' * (length - filled_len)
    return f"[{bar}] {progress:.1f}%"


def format_media_info(media_info) -> str:
    """Format a MediaInfo object as a readable multi-line summary string."""
    info = []
    
    # Try to access properties dynamically
    if hasattr(media_info, 'video_tracks') and media_info.video_tracks:
        vt = media_info.video_tracks[0]
        info.append("🎬 **Video Info:**")
        codec = getattr(vt, 'codec', 'Unknown')
        width = getattr(vt, 'width', 'Unknown')
        height = getattr(vt, 'height', 'Unknown')
        fps = getattr(vt, 'fps', 'Unknown')
        duration = format_duration(getattr(media_info, 'duration', 0))
        info.append(f"  • Resolution: {width}x{height}")
        info.append(f"  • Codec: {codec}")
        info.append(f"  • FPS: {fps}")
        info.append(f"  • Duration: {duration}")
    
    if hasattr(media_info, 'audio_tracks') and media_info.audio_tracks:
        info.append("\n🔊 **Audio Tracks:**")
        for i, at in enumerate(media_info.audio_tracks):
            codec = getattr(at, 'codec', 'Unknown')
            lang = getattr(at, 'language', 'Unknown')
            channels = getattr(at, 'channels', 'Unknown')
            bitrate = getattr(at, 'bitrate', 0)
            bitrate_str = format_file_size(bitrate) + "/s" if bitrate else "Unknown"
            is_default = " (Default)" if getattr(at, 'is_default', False) else ""
            info.append(f"  • #{i+1} - {lang}{is_default} - {codec} ({channels}ch, {bitrate_str})")
            
    if hasattr(media_info, 'subtitle_tracks'):
        info.append(f"\n💬 **Subtitles:** {len(media_info.subtitle_tracks)}")
        
    if hasattr(media_info, 'file_size'):
        info.append(f"\n📦 **File Size:** {format_file_size(media_info.file_size)}")
        
    return "\n".join(info)
