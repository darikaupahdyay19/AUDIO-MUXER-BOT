import asyncio
import logging
import os
import tempfile
import numpy as np
import scipy.signal
import librosa
from pathlib import Path
from typing import TYPE_CHECKING, Tuple, Optional

from models.schemas import SyncResult, DriftResult

if TYPE_CHECKING:
    from core.engine import FFmpegEngine

logger = logging.getLogger(__name__)

class SyncDetector:
    """Audio sync detection using cross-correlation and waveform analysis."""
    
    def __init__(self, ffmpeg_engine: 'FFmpegEngine', sample_rate: int = 16000, analysis_duration: float = 120.0, analysis_start: float = 30.0):
        self.engine = ffmpeg_engine
        self.sample_rate = sample_rate
        self.analysis_duration = analysis_duration
        self.analysis_start = analysis_start
    
    async def detect_offset_cross_correlation(self, reference_path: str, target_path: str) -> SyncResult:
        """Detect time offset between two audio signals using FFT cross-correlation."""
        ref_temp = await self._extract_audio_temp(reference_path)
        target_temp = await self._extract_audio_temp(target_path)
        
        try:
            loop = asyncio.get_event_loop()
            
            # Load audio windows
            ref_signal = await loop.run_in_executor(None, self._load_audio_window, ref_temp)
            target_signal = await loop.run_in_executor(None, self._load_audio_window, target_temp)
            
            # Compute cross-correlation
            offset_seconds, confidence = await loop.run_in_executor(
                None, self._compute_cross_correlation, ref_signal, target_signal
            )
            
            return SyncResult(
                offset_ms=offset_seconds * 1000.0,
                confidence=confidence,
                method="cross_correlation"
            )
            
        finally:
            if os.path.exists(ref_temp):
                os.remove(ref_temp)
            if os.path.exists(target_temp):
                os.remove(target_temp)
    
    async def detect_offset_waveform(self, reference_path: str, target_path: str) -> SyncResult:
        """Detect offset using amplitude envelope comparison."""
        ref_temp = await self._extract_audio_temp(reference_path)
        target_temp = await self._extract_audio_temp(target_path)
        
        def process_waveform(ref_file: str, target_file: str) -> Tuple[float, float]:
            ref_sig = self._load_audio_window(ref_file)
            tgt_sig = self._load_audio_window(target_file)
            
            # Compute RMS envelope
            ref_env = librosa.feature.rms(y=ref_sig, frame_length=2048, hop_length=512)[0]
            tgt_env = librosa.feature.rms(y=tgt_sig, frame_length=2048, hop_length=512)[0]
            
            # Cross-correlate envelopes
            ref_norm = (ref_env - np.mean(ref_env)) / (np.std(ref_env) + 1e-9)
            tgt_norm = (tgt_env - np.mean(tgt_env)) / (np.std(tgt_env) + 1e-9)
            
            correlation = scipy.signal.correlate(ref_norm, tgt_norm, mode='full', method='fft')
            lags = scipy.signal.correlation_lags(len(ref_norm), len(tgt_norm), mode='full')
            
            best_idx = np.argmax(correlation)
            peak_lag_frames = lags[best_idx]
            
            # Convert frames to seconds
            offset_seconds = (peak_lag_frames * 512) / self.sample_rate
            confidence = float(correlation[best_idx] / (np.linalg.norm(ref_norm) * np.linalg.norm(tgt_norm)))
            
            return offset_seconds, confidence

        try:
            loop = asyncio.get_event_loop()
            offset_seconds, confidence = await loop.run_in_executor(
                None, process_waveform, ref_temp, target_temp
            )
            
            return SyncResult(
                offset_ms=offset_seconds * 1000.0,
                confidence=confidence,
                method="waveform"
            )
        finally:
            if os.path.exists(ref_temp):
                os.remove(ref_temp)
            if os.path.exists(target_temp):
                os.remove(target_temp)
    
    async def detect_drift(self, reference_path: str, target_path: str, segment_length: float = 300.0) -> DriftResult:
        """Detect gradual drift over long videos."""
        ref_info = await self.engine.probe(reference_path)
        duration = float(ref_info.get('format', {}).get('duration', 0))
        
        if duration < segment_length * 2:
            result = await self.detect_offset_cross_correlation(reference_path, target_path)
            return DriftResult(initial_offset_ms=result.offset_ms, drift_rate_ms_per_hour=0.0, confidence=result.confidence)
        
        segments = []
        times = [30.0, duration / 2, duration - segment_length - 30.0]
        for t in times:
            if t > duration - 10:
                continue
            
            old_start = self.analysis_start
            old_dur = self.analysis_duration
            self.analysis_start = t
            self.analysis_duration = min(segment_length, duration - t)
            
            try:
                res = await self.detect_offset_cross_correlation(reference_path, target_path)
                segments.append((t, res.offset_ms, res.confidence))
            finally:
                self.analysis_start = old_start
                self.analysis_duration = old_dur
        
        if len(segments) < 2:
            result = await self.detect_offset_cross_correlation(reference_path, target_path)
            return DriftResult(initial_offset_ms=result.offset_ms, drift_rate_ms_per_hour=0.0, confidence=result.confidence)
            
        times_arr = np.array([s[0] for s in segments])
        offsets_arr = np.array([s[1] for s in segments])
        confidences = [s[2] for s in segments]
        avg_confidence = sum(confidences) / len(confidences)
        
        slope, intercept = np.polyfit(times_arr, offsets_arr, 1)
        drift_rate_ms_per_hour = slope * 3600.0
        
        return DriftResult(
            initial_offset_ms=intercept,
            drift_rate_ms_per_hour=drift_rate_ms_per_hour,
            confidence=avg_confidence
        )
    
    async def auto_sync(self, reference_path: str, target_path: str, output_path: str, method: str = 'cross_correlation') -> SyncResult:
        """Detect and fix sync issues automatically."""
        if method == 'waveform':
            result = await self.detect_offset_waveform(reference_path, target_path)
        else:
            result = await self.detect_offset_cross_correlation(reference_path, target_path)
            
        if abs(result.offset_ms) > 10.0:
            delay_ms = result.offset_ms
            cmd = []
            if delay_ms > 0:
                cmd = [
                    "-i", target_path,
                    "-af", f"adelay={int(delay_ms)}|{int(delay_ms)}",
                    "-c:a", "aac",
                    "-y", output_path
                ]
            else:
                delay = int(abs(delay_ms))
                cmd = [
                    "-i", target_path,
                    "-af", f"adelay={delay}|{delay}",
                    "-c:a", "aac",
                    "-y", output_path
                ]
            await self.engine.run_command(cmd)
        else:
            cmd = ["-i", target_path, "-c", "copy", "-y", output_path]
            await self.engine.run_command(cmd)
            
        return result
    
    async def _extract_audio_temp(self, file_path: str) -> str:
        """Extract audio from file to temp WAV for analysis."""
        fd, temp_path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        
        cmd = [
            "-i", file_path,
            "-vn",
            "-ac", "1",
            "-ar", str(self.sample_rate),
            "-c:a", "pcm_s16le",
            "-y", temp_path
        ]
        
        success, _ = await self.engine.run_command(cmd)
        if not success:
            logger.error(f"Failed to extract audio from {file_path}")
            
        return temp_path
    
    def _load_audio_window(self, file_path: str) -> np.ndarray:
        """Load audio window for analysis (synchronous, run in executor)."""
        y, _ = librosa.load(file_path, sr=self.sample_rate, mono=True, offset=self.analysis_start, duration=self.analysis_duration)
        return y
    
    def _compute_cross_correlation(self, ref_signal: np.ndarray, target_signal: np.ndarray) -> Tuple[float, float]:
        """Compute cross-correlation and return (offset_seconds, confidence)."""
        ref_norm = (ref_signal - np.mean(ref_signal)) / (np.std(ref_signal) + 1e-9)
        target_norm = (target_signal - np.mean(target_signal)) / (np.std(target_signal) + 1e-9)
        
        correlation = scipy.signal.correlate(ref_norm, target_norm, mode='full', method='fft')
        lags = scipy.signal.correlation_lags(len(ref_norm), len(target_norm), mode='full')
        
        best_idx = np.argmax(correlation)
        peak_lag = lags[best_idx]
        offset_seconds = peak_lag / self.sample_rate
        
        confidence = float(correlation[best_idx] / (np.linalg.norm(ref_norm) * np.linalg.norm(target_norm)))
        
        return offset_seconds, confidence
