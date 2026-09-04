from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List, Dict, Any

class JobStatus(str, Enum):
    PENDING = 'PENDING'
    PROCESSING = 'PROCESSING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'

class Operation(str, Enum):
    EXTRACT_AUDIO = 'extract_audio'
    ADD_TRACK = 'add_track'
    REPLACE_TRACK = 'replace_track'
    REMOVE_TRACK = 'remove_track'
    CONVERT_AUDIO = 'convert_audio'
    ADJUST_VOLUME = 'adjust_volume'
    NORMALIZE = 'normalize'
    MERGE_AUDIO = 'merge_audio'
    SYNC_DETECT = 'sync_detect'
    SYNC_FIX = 'sync_fix'
    TRIM = 'trim'
    REMOVE_SILENCE = 'remove_silence'
    SMART_TRIM = 'smart_trim'
    LIST_TRACKS = 'list_tracks'
    SET_DEFAULT_TRACK = 'set_default_track'
    REORDER_TRACKS = 'reorder_tracks'
    LABEL_TRACK = 'label_track'

class AudioTrack(BaseModel):
    index: int
    codec: str
    codec_long: str
    sample_rate: int
    channels: int
    channel_layout: str = ""
    bitrate: Optional[int] = None
    language: Optional[str] = None
    title: Optional[str] = None
    is_default: bool = False
    duration: Optional[float] = None

class MediaInfo(BaseModel):
    file_path: str
    file_size: int
    format_name: str
    format_long_name: str
    duration: float
    bitrate: int
    video_codec: Optional[str] = None
    video_codec_long: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    frame_rate: Optional[float] = None
    video_bitrate: Optional[int] = None
    audio_tracks: List[AudioTrack] = Field(default_factory=list)
    subtitle_count: int = 0
    chapter_count: int = 0

class SyncResult(BaseModel):
    offset_ms: float
    offset_seconds: float
    confidence: float
    method: str
    details: Optional[str] = None

class DriftResult(BaseModel):
    initial_offset_ms: float
    drift_rate_ms_per_hour: float
    segments: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float

class SilenceSegment(BaseModel):
    start: float
    end: float
    duration: float

class TrimParams(BaseModel):
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
class ProcessingProgress(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = 0.0
    message: Optional[str] = None
    
class AudioTrackInput(BaseModel):
    path: str
    language: str
    title: Optional[str] = None
    is_default: bool = False

class LoudnessInfo(BaseModel):
    integrated_loudness: float
    true_peak: float
    loudness_range: float
    threshold: float
