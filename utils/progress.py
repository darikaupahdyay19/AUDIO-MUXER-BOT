import asyncio
import re
import time
from typing import Callable, Awaitable

class FFmpegProgress:
    """Parses FFmpeg progress output and calls back with percentage."""
    
    def __init__(self, total_duration_sec: float, callback: Callable[[float], Awaitable[None]] | None = None, update_interval: float = 2.0):
        self.total_duration_sec = total_duration_sec
        self.callback = callback
        self.update_interval = update_interval  # Minimum seconds between callback calls
        self._last_callback_time = 0.0
        self._last_progress = 0.0
        self._time_regex = re.compile(r'out_time_us=(\d+)')
        self._time_regex2 = re.compile(r'time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})')
    
    async def parse_line(self, line: str) -> float | None:
        """Parse a line of FFmpeg progress output. Returns progress percentage or None."""
        # Try out_time_us format (from -progress pipe:1)
        match = self._time_regex.search(line)
        if match and self.total_duration_sec > 0:
            current_sec = int(match.group(1)) / 1_000_000.0
            progress = min(100.0, (current_sec / self.total_duration_sec) * 100.0)
            return await self._maybe_callback(progress)
        
        # Try time=HH:MM:SS.ms format (from stderr)
        match = self._time_regex2.search(line)
        if match and self.total_duration_sec > 0:
            h, m, s, cs = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
            current_sec = h * 3600 + m * 60 + s + cs / 100.0
            progress = min(100.0, (current_sec / self.total_duration_sec) * 100.0)
            return await self._maybe_callback(progress)
        
        return None
    
    async def _maybe_callback(self, progress: float) -> float:
        """Call callback if enough time has passed since last call."""
        self._last_progress = progress
        now = time.monotonic()
        if self.callback and (now - self._last_callback_time) >= self.update_interval:
            self._last_callback_time = now
            await self.callback(progress)
        return progress
    
    @property
    def current_progress(self) -> float:
        return self._last_progress


async def run_ffmpeg_with_progress(cmd: list[str], total_duration_sec: float, progress_callback=None) -> tuple[bool, str]:
    """
    Runs FFmpeg command as asyncio subprocess.
    Injects `-progress pipe:1 -nostats` into the command.
    Returns (success: bool, stderr_output: str).
    Handles asyncio.CancelledError by terminating the process.
    """
    if not cmd:
        return False, "Empty command"
        
    cmd_copy = cmd.copy()
    if cmd_copy[0] != "ffmpeg":
        cmd_copy.insert(0, "ffmpeg")
        
    # Inject progress flags if not present
    if "-progress" not in cmd_copy:
        try:
            input_idx = cmd_copy.index("-i")
            cmd_copy.insert(input_idx, "-progress")
            cmd_copy.insert(input_idx + 1, "pipe:1")
            cmd_copy.insert(input_idx + 2, "-nostats")
        except ValueError:
            # If no -i, just put it after ffmpeg
            cmd_copy.insert(1, "-progress")
            cmd_copy.insert(2, "pipe:1")
            cmd_copy.insert(3, "-nostats")
            
    progress_parser = FFmpegProgress(total_duration_sec, progress_callback)
    stderr_lines = []
    process = None
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd_copy,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        async def read_stdout():
            if process.stdout:
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    await progress_parser.parse_line(line_str)
                    
        async def read_stderr():
            if process.stderr:
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    stderr_lines.append(line_str)
                    await progress_parser.parse_line(line_str)
                    
        await asyncio.gather(
            read_stdout(),
            read_stderr(),
            process.wait()
        )
        
        success = process.returncode == 0
        return success, "\n".join(stderr_lines)
        
    except asyncio.CancelledError:
        if process and process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        raise
