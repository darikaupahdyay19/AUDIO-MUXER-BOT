import asyncio
import logging
import re
from typing import TYPE_CHECKING, List, Tuple, Optional

from models.schemas import SilenceSegment

if TYPE_CHECKING:
    from core.engine import FFmpegEngine

logger = logging.getLogger(__name__)

class Trimmer:
    def __init__(self, ffmpeg_engine: 'FFmpegEngine'):
        self.engine = ffmpeg_engine
    
    async def trim_by_time(self, input_path: str, output_path: str, start_time: Optional[float] = None, end_time: Optional[float] = None, codec: str = 'copy', progress_callback=None) -> bool:
        """Trim file by start/end time."""
        cmd = []
        if codec == 'copy':
            if start_time is not None:
                cmd.extend(["-ss", str(start_time)])
            cmd.extend(["-i", input_path])
            if end_time is not None:
                if start_time is not None:
                    cmd.extend(["-to", str(end_time - start_time)])
                else:
                    cmd.extend(["-to", str(end_time)])
            cmd.extend(["-c", "copy", "-y", output_path])
        else:
            cmd.extend(["-i", input_path])
            if start_time is not None:
                cmd.extend(["-ss", str(start_time)])
            if end_time is not None:
                cmd.extend(["-to", str(end_time)])
            cmd.extend(["-c", codec, "-y", output_path])
            
        success, _ = await self.engine.run_command(cmd, progress_callback=progress_callback)
        return success
    
    async def detect_silence(self, input_path: str, threshold_db: float = -40, min_duration: float = 0.5) -> List[SilenceSegment]:
        """Detect silent segments using FFmpeg silencedetect filter."""
        cmd = [
            "-i", input_path,
            "-af", f"silencedetect=noise={threshold_db}dB:d={min_duration}",
            "-f", "null",
            "-"
        ]
        
        success, output = await self.engine.run_command(cmd)
        
        segments = []
        current_start = None
        
        for line in output.splitlines():
            start_match = re.search(r'silence_start:\s+([\d\.]+)', line)
            end_match = re.search(r'silence_end:\s+([\d\.]+)\s+\|\s+silence_duration:\s+([\d\.]+)', line)
            
            if start_match:
                current_start = float(start_match.group(1))
            elif end_match and current_start is not None:
                end_time = float(end_match.group(1))
                duration = float(end_match.group(2))
                segments.append(SilenceSegment(
                    start=current_start,
                    end=end_time,
                    duration=duration
                ))
                current_start = None
                
        return segments
    
    async def remove_silence(self, input_path: str, output_path: str, threshold_db: float = -40, min_duration: float = 0.5, padding: float = 0.1, progress_callback=None) -> Tuple[bool, List[SilenceSegment]]:
        """Remove silent segments from audio/video."""
        segments = await self.detect_silence(input_path, threshold_db, min_duration)
        if not segments:
            # No silence detected, just copy
            success = await self.trim_by_time(input_path, output_path, progress_callback=progress_callback)
            return success, []
            
        # Use silenceremove filter
        filter_str = f"silenceremove=start_periods=1:start_duration={min_duration}:start_threshold={threshold_db}dB:stop_periods=-1:stop_duration={min_duration}:stop_threshold={threshold_db}dB"
        cmd = [
            "-i", input_path,
            "-af", filter_str,
            "-c:v", "copy",
            "-y", output_path
        ]
        
        success, _ = await self.engine.run_command(cmd, progress_callback=progress_callback)
        return success, segments
    
    async def smart_trim(self, input_path: str, output_path: str, progress_callback=None) -> bool:
        """Intelligent trimming: remove leading/trailing silence."""
        segments = await self.detect_silence(input_path, threshold_db=-45, min_duration=0.5)
        
        probe = await self.engine.probe(input_path)
        duration = float(probe.get('format', {}).get('duration', 0.0))
        
        start_trim = 0.0
        end_trim = duration
        
        for seg in segments:
            if seg.start < 0.5:
                start_trim = seg.end
            if seg.end > duration - 0.5:
                end_trim = seg.start
                
        if start_trim == 0.0 and end_trim == duration:
            return await self.trim_by_time(input_path, output_path, progress_callback=progress_callback)
            
        return await self.trim_by_time(input_path, output_path, start_time=start_trim, end_time=end_trim, codec='copy', progress_callback=progress_callback)
    
    async def trim_to_match(self, longer_path: str, shorter_path: str, output_path: str, progress_callback=None) -> bool:
        """Trim the longer file to match the shorter file's duration."""
        short_probe = await self.engine.probe(shorter_path)
        duration = float(short_probe.get('format', {}).get('duration', 0.0))
        
        return await self.trim_by_time(longer_path, output_path, start_time=0.0, end_time=duration, codec='copy', progress_callback=progress_callback)
    
    async def get_silence_summary(self, silence_segments: List[SilenceSegment]) -> str:
        """Format silence detection results as a human-readable summary."""
        if not silence_segments:
            return "No silence detected."
        
        lines = [f"Detected {len(silence_segments)} silent segments:"]
        total_silence = sum(seg.duration for seg in silence_segments)
        
        for i, seg in enumerate(silence_segments):
            lines.append(f"  {i+1}: {seg.start:.2f}s - {seg.end:.2f}s (duration: {seg.duration:.2f}s)")
            
        lines.append(f"Total silence duration: {total_silence:.2f}s")
        return "\n".join(lines)
