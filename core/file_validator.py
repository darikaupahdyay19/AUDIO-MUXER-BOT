import os
from models.schemas import MediaInfo, AudioTrack
from core.ffmpeg_engine import FFmpegEngine
import logging

try:
    from bot import config
except ImportError:
    config = type('Config', (), {'MAX_FILE_SIZE': 2 * 1024 * 1024 * 1024, 'SUPPORTED_EXTENSIONS': ['.mkv', '.mp4', '.m4a', '.mp3', '.mka']})

logger = logging.getLogger(__name__)

class FileValidator:
    def __init__(self, ffmpeg_engine: 'FFmpegEngine'):
        self.engine = ffmpeg_engine
    
    async def validate(self, file_path: str) -> tuple[bool, str, 'MediaInfo | None']:
        """Validate a media file. Returns (valid, message, media_info)."""
        if not os.path.exists(file_path):
            return False, "File does not exist", None
            
        _, ext = os.path.splitext(file_path)
        if ext.lower() not in getattr(config, 'SUPPORTED_EXTENSIONS', ['.mkv', '.mp4', '.mka', '.m4a', '.mp3']):
            return False, f"Unsupported extension: {ext}", None
            
        file_size = os.path.getsize(file_path)
        max_size = getattr(config, 'MAX_FILE_SIZE', 2 * 1024 * 1024 * 1024)
        if file_size > max_size:
            return False, f"File too large: {file_size} > {max_size}", None
            
        try:
            probe_data = await self.engine.probe(file_path)
            media_info = self.parse_media_info(file_path, probe_data)
            return True, "Valid media file", media_info
        except Exception as e:
            return False, f"Validation failed during probe: {e}", None
            
    def parse_media_info(self, file_path: str, probe_data: dict) -> 'MediaInfo':
        """Parse ffprobe JSON output into a MediaInfo model."""
        format_info = probe_data.get('format', {})
        duration = float(format_info.get('duration', 0.0))
        size = int(format_info.get('size', 0))
        
        has_video = False
        audio_tracks = []
        
        for i, stream in enumerate(probe_data.get('streams', [])):
            if stream.get('codec_type') == 'video':
                has_video = True
            elif stream.get('codec_type') == 'audio':
                tags = stream.get('tags', {})
                disposition = stream.get('disposition', {})
                audio_tracks.append(AudioTrack(
                    index=stream.get('index', i),
                    codec=stream.get('codec_name', 'unknown'),
                    channels=stream.get('channels', 2),
                    language=tags.get('language', 'und'),
                    title=tags.get('title'),
                    is_default=bool(disposition.get('default', 0))
                ))
                
        return MediaInfo(
            file_path=file_path,
            duration=duration,
            size=size,
            has_video=has_video,
            audio_tracks=audio_tracks
        )
    
    async def check_integrity(self, file_path: str) -> tuple[bool, str]:
        """Quick integrity check by probing the file."""
        try:
            await self.engine.probe(file_path)
            return True, "Integrity check passed"
        except Exception as e:
            return False, f"Integrity check failed: {e}"
    
    async def attempt_repair(self, file_path: str, output_path: str) -> bool:
        """Attempt to repair a corrupted file using ffmpeg."""
        cmd = [self.engine.ffmpeg, '-err_detect', 'ignore_err', '-i', file_path, '-c', 'copy', output_path]
        ok, _ = await self.engine._run(cmd)
        return ok
