import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
TEMP_DIR = Path(os.getenv('TEMP_DIR', str(BASE_DIR / 'temp')))
DB_PATH = str(BASE_DIR / 'data' / 'audiomuxer.db')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
LOCAL_API_SERVER = os.getenv('LOCAL_API_SERVER', '')  # e.g. http://localhost:8081/bot
LOCAL_MODE = bool(LOCAL_API_SERVER)

# File limits
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '2048'))
MAX_DURATION_HOURS = int(os.getenv('MAX_DURATION_HOURS', '4'))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_DURATION_SECONDS = MAX_DURATION_HOURS * 3600

# Processing
MAX_CONCURRENT_JOBS = int(os.getenv('MAX_CONCURRENT_JOBS', '2'))
CLEANUP_INTERVAL_HOURS = int(os.getenv('CLEANUP_INTERVAL_HOURS', '1'))
CLEANUP_MAX_AGE_HOURS = int(os.getenv('CLEANUP_MAX_AGE_HOURS', '24'))

# Supported formats
VIDEO_FORMATS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.ts', '.m2ts'}
AUDIO_FORMATS = {'.mp3', '.aac', '.wav', '.flac', '.ogg', '.opus', '.m4a', '.ac3', '.eac3', '.dts', '.wma'}
ALL_MEDIA_FORMATS = VIDEO_FORMATS | AUDIO_FORMATS

# Audio codecs mapping (extension -> ffmpeg codec name)
AUDIO_CODEC_MAP = {
    '.mp3': 'libmp3lame',
    '.aac': 'aac',
    '.wav': 'pcm_s16le',
    '.flac': 'flac',
    '.ogg': 'libvorbis',
    '.opus': 'libopus',
    '.m4a': 'aac',
    '.ac3': 'ac3',
    '.eac3': 'eac3',
    '.dts': 'dca',
    '.wma': 'wmav2',
}

# Default processing parameters
DEFAULT_AUDIO_BITRATE = '192k'
DEFAULT_SAMPLE_RATE = 48000
DEFAULT_LOUDNESS_TARGET = -16.0  # LUFS

# Silence detection defaults
SILENCE_THRESHOLD_DB = -40
SILENCE_MIN_DURATION = 0.5  # seconds
SILENCE_PADDING = 0.1  # seconds

# Sync detection defaults
SYNC_SAMPLE_RATE = 16000  # Hz, downsampled for efficiency
SYNC_ANALYSIS_DURATION = 120.0  # seconds
SYNC_ANALYSIS_START = 30.0  # seconds offset to skip intros
SYNC_DRIFT_SEGMENT_LENGTH = 300.0  # seconds (5 min segments)

# ISO 639-2 language codes
LANGUAGE_CODES = {
    'English': 'eng', 'Spanish': 'spa', 'French': 'fra', 'German': 'deu',
    'Chinese': 'zho', 'Japanese': 'jpn', 'Korean': 'kor', 'Hindi': 'hin',
    'Arabic': 'ara', 'Portuguese': 'por', 'Russian': 'rus', 'Italian': 'ita',
    'Dutch': 'nld', 'Polish': 'pol', 'Turkish': 'tur', 'Vietnamese': 'vie',
    'Thai': 'tha', 'Indonesian': 'ind',
}
LANGUAGE_NAMES = {v: k for k, v in LANGUAGE_CODES.items()}

# Quality presets
QUALITY_PRESETS = {
    'high': {'audio_bitrate': '320k', 'sample_rate': 48000},
    'medium': {'audio_bitrate': '192k', 'sample_rate': 48000},
    'low': {'audio_bitrate': '128k', 'sample_rate': 44100},
    'voice': {'audio_bitrate': '64k', 'sample_rate': 16000},
}

def ensure_directories():
    """Create required directories if they don't exist."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
