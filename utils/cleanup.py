import asyncio
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

async def cleanup_temp_files(temp_dir: str | Path, max_age_hours: int = 24) -> int:
    """Delete files older than max_age_hours in temp_dir. Returns count of deleted files."""
    deleted_count = 0
    now = time.time()
    max_age_seconds = max_age_hours * 3600
    
    path = Path(temp_dir)
    if not path.exists() or not path.is_dir():
        return 0
        
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    try:
                        stat = entry.stat()
                        age = now - stat.st_mtime
                        if age > max_age_seconds:
                            os.remove(entry.path)
                            deleted_count += 1
                    except (PermissionError, OSError) as e:
                        logger.warning(f"Failed to delete {entry.path}: {e}")
    except (PermissionError, OSError) as e:
        logger.error(f"Failed to scan {temp_dir}: {e}")
        
    return deleted_count

async def start_cleanup_daemon(temp_dir: str | Path, interval_hours: int = 1, max_age_hours: int = 24) -> asyncio.Task:
    """Start a background asyncio task that runs cleanup_temp_files periodically."""
    
    async def cleanup_loop():
        interval_seconds = interval_hours * 3600
        logger.info(f"Starting cleanup daemon for {temp_dir} (interval: {interval_hours}h, max age: {max_age_hours}h)")
        while True:
            try:
                deleted = await cleanup_temp_files(temp_dir, max_age_hours)
                if deleted > 0:
                    logger.info(f"Cleanup daemon deleted {deleted} files from {temp_dir}")
            except Exception as e:
                logger.error(f"Error in cleanup daemon: {e}")
            await asyncio.sleep(interval_seconds)
            
    return asyncio.create_task(cleanup_loop())

def get_temp_dir_size(temp_dir: str | Path) -> int:
    """Return total size in bytes of all files in temp_dir."""
    total_size = 0
    path = Path(temp_dir)
    if not path.exists() or not path.is_dir():
        return 0
        
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    try:
                        total_size += entry.stat().st_size
                    except (PermissionError, OSError):
                        pass
    except (PermissionError, OSError):
        pass
        
    return total_size
