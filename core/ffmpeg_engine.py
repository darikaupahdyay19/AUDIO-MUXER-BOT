import asyncio
import json
import logging
import os
import shutil
import re
from pathlib import Path
from typing import Callable, Awaitable

# Assuming a utils.progress module exists based on instructions
try:
    from utils.progress import run_ffmpeg_with_progress
except ImportError:
    # Dummy fallback if not present
    async def run_ffmpeg_with_progress(cmd: list[str], progress_callback=None, total_duration=None):
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        return proc.returncode == 0, stderr.decode()

logger = logging.getLogger(__name__)

class FFmpegEngine:
    """Async wrapper around FFmpeg for video/audio processing."""
    
    def __init__(self, ffmpeg_path: str = 'ffmpeg', ffprobe_path: str = 'ffprobe'):
        self.ffmpeg = ffmpeg_path
        self.ffprobe = ffprobe_path
    
    async def check_installation(self) -> tuple[bool, str]:
        """Check if FFmpeg and FFprobe are available. Returns (ok, version_string)."""
        try:
            proc = await asyncio.create_subprocess_exec(self.ffmpeg, '-version', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                first_line = stdout.decode().split('\\n')[0]
                return True, first_line
            return False, "FFmpeg returned non-zero exit code"
        except Exception as e:
            return False, str(e)
    
    async def probe(self, file_path: str) -> dict:
        """Run ffprobe and return parsed JSON output with format and streams info."""
        cmd = [self.ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', '-show_chapters', file_path]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f'ffprobe failed: {stderr.decode()}')
            return json.loads(stdout.decode())
        except Exception as e:
            logger.error(f"Error probing {file_path}: {e}")
            raise

    async def extract_audio(self, input_path: str, output_path: str, track_index: int = 0, codec: str = 'copy', bitrate: str | None = None, progress_callback: Callable[[float], Awaitable[None]] | None = None) -> bool:
        """Extract audio track from video file."""
        cmd = [self.ffmpeg, '-y', '-i', input_path, '-map', f'0:a:{track_index}', '-c:a', codec]
        if bitrate and codec != 'copy':
            cmd.extend(['-b:a', bitrate])
        cmd.append(output_path)
        ok, _ = await self._run(cmd, progress_callback)
        return ok

    async def add_audio_track(self, video_path: str, audio_path: str, output_path: str, language: str = 'und', title: str | None = None, set_default: bool = False, codec: str = 'copy') -> bool:
        """Add a new audio track to a video file. Preserves all existing streams."""
        try:
            probe_data = await self.probe(video_path)
            audio_streams = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'audio']
            new_track_idx = len(audio_streams)
        except Exception:
            new_track_idx = 0
            
        cmd = [self.ffmpeg, '-y', '-i', video_path, '-i', audio_path, '-map', '0', '-map', '1:a', '-c', codec, f'-metadata:s:a:{new_track_idx}', f'language={language}']
        if title:
            cmd.extend([f'-metadata:s:a:{new_track_idx}', f'title={title}'])
        if set_default:
            cmd.extend([f'-disposition:a:{new_track_idx}', 'default'])
        cmd.append(output_path)
        ok, _ = await self._run(cmd)
        return ok
        
    async def replace_audio_track(self, video_path: str, audio_path: str, output_path: str, track_index: int = 0, codec: str = 'copy') -> bool:
        """Replace a specific audio track in a video."""
        cmd = [self.ffmpeg, '-y', '-i', video_path, '-i', audio_path, '-map', '0', f'-map', f'-0:a:{track_index}', '-map', '1:a', '-c', codec, output_path]
        ok, _ = await self._run(cmd)
        return ok

    async def remove_audio_track(self, video_path: str, output_path: str, track_index: int) -> bool:
        """Remove a specific audio track from a video."""
        cmd = [self.ffmpeg, '-y', '-i', video_path, '-map', '0', f'-map', f'-0:a:{track_index}', '-c', 'copy', output_path]
        ok, _ = await self._run(cmd)
        return ok

    async def mux_multiple_tracks(self, video_path: str, audio_tracks: list[dict], output_path: str) -> bool:
        """Mux video with multiple audio tracks."""
        cmd = [self.ffmpeg, '-y', '-i', video_path]
        for t in audio_tracks:
            cmd.extend(['-i', t['path']])
        
        cmd.extend(['-map', '0:v', '-map', '0:s?'])
        
        for i in range(len(audio_tracks)):
            cmd.extend(['-map', f'{i+1}:a'])
        
        cmd.extend(['-c', 'copy'])
        
        for i, t in enumerate(audio_tracks):
            lang = t.get('language', 'und')
            cmd.extend([f'-metadata:s:a:{i}', f'language={lang}'])
            if 'title' in t and t['title']:
                cmd.extend([f'-metadata:s:a:{i}', f'title={t["title"]}'])
            if t.get('is_default'):
                cmd.extend([f'-disposition:a:{i}', 'default'])
            else:
                cmd.extend([f'-disposition:a:{i}', '0'])
        
        cmd.append(output_path)
        ok, _ = await self._run(cmd)
        return ok
        
    async def convert_audio(self, input_path: str, output_path: str, codec: str | None = None, bitrate: str | None = None, sample_rate: int | None = None, channels: int | None = None, progress_callback=None) -> bool:
        """Convert audio format/codec/bitrate."""
        cmd = [self.ffmpeg, '-y', '-i', input_path]
        if not codec:
            # simple heuristic or assume ffmpeg guesses from ext
            ext = os.path.splitext(output_path)[1].lower()
            if ext == '.mp3': codec = 'libmp3lame'
            elif ext == '.aac': codec = 'aac'
            elif ext == '.m4a': codec = 'aac'
            elif ext == '.ogg': codec = 'libvorbis'
            elif ext == '.opus': codec = 'libopus'
            else: codec = 'copy'
        cmd.extend(['-c:a', codec])
        if bitrate and codec != 'copy':
            cmd.extend(['-b:a', bitrate])
        if sample_rate:
            cmd.extend(['-ar', str(sample_rate)])
        if channels:
            cmd.extend(['-ac', str(channels)])
        cmd.append(output_path)
        ok, _ = await self._run(cmd, progress_callback)
        return ok

    async def adjust_volume(self, input_path: str, output_path: str, gain_db: float, progress_callback=None) -> bool:
        """Adjust audio volume by gain_db decibels."""
        cmd = [self.ffmpeg, '-y', '-i', input_path, '-af', f'volume={gain_db}dB', output_path]
        ok, _ = await self._run(cmd, progress_callback)
        return ok

    async def normalize_audio(self, input_path: str, output_path: str, target_loudness: float = -16.0, progress_callback=None) -> bool:
        """Normalize audio using EBU R128 loudnorm filter (two-pass)."""
        # Pass 1
        pass1_cmd = [
            self.ffmpeg, '-y', '-i', input_path,
            '-af', f'loudnorm=I={target_loudness}:TP=-1.5:LRA=11:print_format=json',
            '-f', 'null', '-'
        ]
        proc = await asyncio.create_subprocess_exec(*pass1_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr = await proc.communicate()
        
        # Parse pass 1 output
        measured_i = None
        measured_tp = None
        measured_lra = None
        measured_thresh = None
        offset = None
        
        try:
            # find JSON block in stderr
            err_str = stderr.decode()
            json_match = re.search(r'\{.*\}', err_str, re.DOTALL)
            if json_match:
                stats = json.loads(json_match.group(0))
                measured_i = stats.get('input_i')
                measured_tp = stats.get('input_tp')
                measured_lra = stats.get('input_lra')
                measured_thresh = stats.get('input_thresh')
                offset = stats.get('target_offset')
        except Exception as e:
            logger.error(f"Failed to parse loudnorm stats: {e}")
            return False
            
        if not all([measured_i, measured_tp, measured_lra, measured_thresh, offset]):
            logger.error("Could not extract loudnorm stats")
            return False

        # Pass 2
        pass2_cmd = [
            self.ffmpeg, '-y', '-i', input_path,
            '-af', f'loudnorm=I={target_loudness}:TP=-1.5:LRA=11:measured_I={measured_i}:measured_TP={measured_tp}:measured_LRA={measured_lra}:measured_thresh={measured_thresh}:offset={offset}:linear=true',
            output_path
        ]
        ok, _ = await self._run(pass2_cmd, progress_callback)
        return ok

    async def merge_audio_files(self, input_paths: list[str], output_path: str, progress_callback=None) -> bool:
        """Concatenate multiple audio files."""
        if not input_paths:
            return False
        
        list_file = Path(output_path).parent / "concat_list.txt"
        try:
            with open(list_file, 'w', encoding='utf-8') as f:
                for p in input_paths:
                    f.write(f"file '{os.path.abspath(p).replace(chr(92), '/')}'\\n")
            
            cmd = [self.ffmpeg, '-y', '-f', 'concat', '-safe', '0', '-i', str(list_file), '-c', 'copy', output_path]
            ok, _ = await self._run(cmd, progress_callback)
            return ok
        finally:
            if list_file.exists():
                os.remove(list_file)

    async def split_audio(self, input_path: str, output_dir: str, timestamps: list[float]) -> list[str]:
        """Split audio at specified timestamps. Returns list of output file paths."""
        outputs = []
        timestamps = sorted(list(set([0.0] + timestamps)))
        
        for i in range(len(timestamps)):
            start = timestamps[i]
            out_file = os.path.join(output_dir, f"segment_{i}.mka")
            cmd = [self.ffmpeg, '-y', '-ss', str(start)]
            if i < len(timestamps) - 1:
                cmd.extend(['-to', str(timestamps[i+1])])
            cmd.extend(['-i', input_path, '-c', 'copy', out_file])
            ok, _ = await self._run(cmd)
            if ok and os.path.exists(out_file):
                outputs.append(out_file)
                
        return outputs

    async def apply_delay(self, input_path: str, output_path: str, delay_ms: float, progress_callback=None) -> bool:
        """Apply delay to audio (positive=delay, negative=trim beginning)."""
        if delay_ms >= 0:
            cmd = [self.ffmpeg, '-y', '-i', input_path, '-af', f'adelay={int(delay_ms)}|{int(delay_ms)}', output_path]
        else:
            cmd = [self.ffmpeg, '-y', '-ss', str(abs(delay_ms)/1000.0), '-i', input_path, '-c', 'copy', output_path]
        ok, _ = await self._run(cmd, progress_callback)
        return ok

    async def apply_tempo(self, input_path: str, output_path: str, tempo_factor: float, progress_callback=None) -> bool:
        """Adjust audio tempo for drift correction. tempo_factor: 1.0 = normal."""
        # ffmpeg atempo supports 0.5 to 100.0 natively in newer versions, but typical range is 0.5 to 2.0
        cmd = [self.ffmpeg, '-y', '-i', input_path, '-af', f'atempo={tempo_factor}', output_path]
        ok, _ = await self._run(cmd, progress_callback)
        return ok

    async def _run(self, cmd: list[str], progress_callback=None, total_duration: float | None = None) -> tuple[bool, str]:
        """Internal method to run FFmpeg command with optional progress tracking."""
        logger.debug(f"Running command: {' '.join(cmd)}")
        try:
            ok, err = await run_ffmpeg_with_progress(cmd, progress_callback, total_duration)
            if not ok:
                logger.error(f"FFmpeg command failed: {err}")
            return ok, err
        except Exception as e:
            logger.error(f"Exception running FFmpeg: {e}")
            return False, str(e)
