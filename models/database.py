import aiosqlite
import json
import time
from typing import Optional, List, Dict, Any

async def init_db(db_path: str) -> None:
    """Initialize the SQLite database and create necessary tables."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                chat_id TEXT,
                operation TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                progress REAL DEFAULT 0.0,
                input_file TEXT,
                output_file TEXT,
                parameters TEXT,
                error_message TEXT,
                created_at REAL,
                updated_at REAL,
                completed_at REAL
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS file_metadata (
                file_hash TEXT PRIMARY KEY,
                file_path TEXT,
                metadata TEXT,
                created_at REAL
            )
        """)
        await db.commit()

class JobRepository:
    """Repository for managing job records and file metadata."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        d = dict(row)
        if "parameters" in d and d["parameters"]:
            d["parameters"] = json.loads(d["parameters"])
        if "metadata" in d and d["metadata"]:
            d["metadata"] = json.loads(d["metadata"])
        return d
        
    async def create_job(self, job_id: str, user_id: str, chat_id: Optional[str], operation: str, parameters: dict) -> None:
        """Create a new job record."""
        now = time.time()
        params_str = json.dumps(parameters)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO jobs (job_id, user_id, chat_id, operation, parameters, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, user_id, chat_id, operation, params_str, now, now)
            )
            await db.commit()
            
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a job by its ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_dict(row)
                return None
                
    async def get_user_jobs(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent jobs for a specific user."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", 
                (user_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_dict(row) for row in rows]
                
    async def update_progress(self, job_id: str, status: str, progress: float) -> None:
        """Update job status and progress."""
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE jobs SET status = ?, progress = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status, progress, now, job_id)
            )
            await db.commit()
            
    async def complete_job(self, job_id: str, output_file: str) -> None:
        """Mark a job as completed."""
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE jobs SET status = 'COMPLETED', progress = 100.0, output_file = ?, updated_at = ?, completed_at = ?
                WHERE job_id = ?
                """,
                (output_file, now, now, job_id)
            )
            await db.commit()
            
    async def fail_job(self, job_id: str, error_msg: str) -> None:
        """Mark a job as failed."""
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE jobs SET status = 'FAILED', error_message = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (error_msg, now, job_id)
            )
            await db.commit()
            
    async def cancel_job(self, job_id: str) -> None:
        """Mark a job as cancelled."""
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE jobs SET status = 'CANCELLED', updated_at = ?
                WHERE job_id = ?
                """,
                (now, job_id)
            )
            await db.commit()
            
    async def cache_metadata(self, file_hash: str, file_path: str, metadata: dict) -> None:
        """Cache metadata for a file."""
        now = time.time()
        meta_str = json.dumps(metadata)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO file_metadata (file_hash, file_path, metadata, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (file_hash, file_path, meta_str, now)
            )
            await db.commit()
            
    async def get_cached_metadata(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached metadata by file hash."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM file_metadata WHERE file_hash = ?", (file_hash,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_dict(row)["metadata"]
                return None
                
    async def cleanup_old_jobs(self, max_age_hours: int = 48) -> int:
        """Delete jobs older than the specified number of hours."""
        cutoff_time = time.time() - (max_age_hours * 3600)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM jobs WHERE created_at < ?", (cutoff_time,))
            deleted_count = cursor.rowcount
            await db.commit()
            return deleted_count
