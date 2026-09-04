import asyncio
import json
import logging
import librosa
import numpy as np
from typing import TYPE_CHECKING, List, Optional, Dict

from models.schemas import LoudnessInfo

if TYPE_CHECKING:
    from core.engine import FFmpegEngine

logger = logging.getLogger(__name__)

class AudioAnalyzer:
    def __init__(self, ffmpeg_engine: 'FFmpegEngine'):
        self.engine = ffmpeg_engine
    
    async def analyze_loudness(self, file_path: str) -> LoudnessInfo:
        """Analyze audio loudness using FFmpeg loudnorm filter."""
        cmd = [
            "-i", file_path,
            "-af", "loudnorm=I=-24:LRA=7:tp=-2:print_format=json",
            "-f", "null",
            "-"
        ]
        
        success, output = await self.engine.run_command(cmd)
        
        # Parse JSON from stderr
        json_str = ""
        in_json = False
        for line in output.splitlines():
            if line.strip().startswith("{"):
                in_json = True
            if in_json:
                json_str += line + "\n"
            if in_json and line.strip().startswith("}"):
                break
                
        try:
            data = json.loads(json_str)
            return LoudnessInfo(
                integrated_loudness=float(data.get("input_i", 0.0)),
                true_peak=float(data.get("input_tp", 0.0)),
                lra=float(data.get("input_lra", 0.0)),
                threshold=float(data.get("input_thresh", 0.0))
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse loudness info: {e}")
            return LoudnessInfo(integrated_loudness=0.0, true_peak=0.0, lra=0.0, threshold=0.0)
    
    async def generate_waveform_data(self, file_path: str, num_points: int = 1000) -> List[float]:
        """Generate waveform amplitude data for visualization."""
        def compute_waveform(path: str) -> List[float]:
            y, sr = librosa.load(path, sr=8000, mono=True)
            if len(y) == 0:
                return [0.0] * num_points
                
            hop_length = max(1, len(y) // num_points)
            rms = librosa.feature.rms(y=y, frame_length=min(2048, len(y)), hop_length=hop_length)[0]
            
            # Normalize to 0-1
            if np.max(rms) > 0:
                rms = rms / np.max(rms)
                
            # Interpolate to exactly num_points if needed
            if len(rms) != num_points:
                x = np.linspace(0, 1, len(rms))
                x_new = np.linspace(0, 1, num_points)
                rms = np.interp(x_new, x, rms)
                
            return rms.tolist()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, compute_waveform, file_path)
    
    async def detect_language(self, file_path: str) -> Optional[str]:
        """Attempt to detect audio language from metadata."""
        probe = await self.engine.probe(file_path)
        streams = probe.get("streams", [])
        
        for stream in streams:
            if stream.get("codec_type") == "audio":
                tags = stream.get("tags", {})
                if "language" in tags:
                    return tags["language"]
        return None
    
    async def get_audio_properties(self, file_path: str) -> Dict:
        """Get detailed audio properties."""
        probe = await self.engine.probe(file_path)
        streams = probe.get("streams", [])
        
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if not audio_stream:
            return {}
            
        return {
            "codec_name": audio_stream.get("codec_name"),
            "sample_rate": int(audio_stream.get("sample_rate", 0)),
            "channels": int(audio_stream.get("channels", 0)),
            "bit_rate": int(audio_stream.get("bit_rate", 0)) if audio_stream.get("bit_rate") else None,
            "duration": float(audio_stream.get("duration", 0.0)) if audio_stream.get("duration") else None,
            "tags": audio_stream.get("tags", {})
        }
