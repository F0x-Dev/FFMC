# ffmc/persistence/database.py
"""
SQLite database for tracking conversions and analysis results
Provides persistence, resume capability, and statistics tracking
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from contextlib import contextmanager

from ffmc.analysis.codec_detector import VideoAnalysis
from ffmc.monitoring.logger import get_logger
from ffmc.utils.exceptions import DatabaseError

logger = get_logger('database')


class ConversionDatabase:
    """
    SQLite database manager for conversion tracking
    
    Tables:
    - videos: Video file metadata and analysis
    - conversions: Conversion history and results
    - statistics: Aggregated statistics
    """
    
    SCHEMA_VERSION = 1
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()
        logger.debug(f"Database initialized: {db_path}")
    
    def _initialize_database(self):
        """Create database schema if not exists"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Videos table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    file_size INTEGER NOT NULL,
                    video_codec TEXT NOT NULL,
                    audio_codec TEXT NOT NULL,
                    container TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    fps REAL NOT NULL,
                    duration REAL NOT NULL,
                    bitrate INTEGER NOT NULL,
                    needs_conversion BOOLEAN NOT NULL,
                    analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    probe_data TEXT
                )
            """)
            
            # Conversions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    original_size INTEGER NOT NULL,
                    converted_size INTEGER,
                    compression_ratio REAL,
                    space_saved INTEGER,
                    processing_time REAL,
                    error_message TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (video_id) REFERENCES videos(id)
                )
            """)
            
            # Statistics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_conversions INTEGER DEFAULT 0,
                    successful_conversions INTEGER DEFAULT 0,
                    failed_conversions INTEGER DEFAULT 0,
                    skipped_conversions INTEGER DEFAULT 0,
                    total_original_size INTEGER DEFAULT 0,
                    total_converted_size INTEGER DEFAULT 0,
                    total_space_saved INTEGER DEFAULT 0,
                    total_processing_time REAL DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_videos_path 
                ON videos(file_path)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversions_status 
                ON conversions(status)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversions_video_id 
                ON conversions(video_id)
            """)
            
            # Initialize statistics if empty
            cursor.execute("SELECT COUNT(*) FROM statistics")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO statistics DEFAULT VALUES
                """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            isolation_level='DEFERRED'
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        except sqlite3.Error as e:
            conn.rollback()
            raise DatabaseError(f"Database error: {e}")
        finally:
            conn.close()
    
    def store_analysis(self, video_path: Path, analysis: VideoAnalysis):
        """Store video analysis results"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO videos (
                    file_path, file_size, video_codec, audio_codec,
                    container, resolution, width, height, fps,
                    duration, bitrate, needs_conversion, probe_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(video_path),
                analysis.file_size,
                analysis.video_codec,
                analysis.audio_codec,
                analysis.container,
                analysis.resolution,
                analysis.width,
                analysis.height,
                analysis.fps,
                analysis.duration,
                analysis.bitrate,
                analysis.needs_conversion,
                json.dumps(analysis.probe_data)
            ))
            
            conn.commit()
            logger.debug(f"Stored analysis: {video_path.name}")
    
    def get_analysis(self, video_path: Path) -> Optional[VideoAnalysis]:
        """Retrieve stored video analysis"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM videos WHERE file_path = ?
            """, (str(video_path),))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            # Reconstruct VideoAnalysis object
            return VideoAnalysis(
                file_path=Path(row['file_path']),
                video_codec=row['video_codec'],
                audio_codec=row['audio_codec'],
                container=row['container'],
                resolution=row['resolution'],
                width=row['width'],
                height=row['height'],
                fps=row['fps'],
                duration=row['duration'],
                bitrate=row['bitrate'],
                file_size=row['file_size'],
                needs_conversion=bool(row['needs_conversion']),
                reason="",
                probe_data=json.loads(row['probe_data'])
            )
    
    def mark_started(self, video_path: Path, original_size: int) -> int:
        """Mark conversion as started"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get video_id
            cursor.execute("""
                SELECT id FROM videos WHERE file_path = ?
            """, (str(video_path),))
            
            row = cursor.fetchone()
            if not row:
                raise DatabaseError(f"Video not found in database: {video_path}")
            
            video_id = row['id']
            
            # Insert conversion record
            cursor.execute("""
                INSERT INTO conversions (
                    video_id, file_path, status, original_size, started_at
                ) VALUES (?, ?, 'started', ?, ?)
            """, (video_id, str(video_path), original_size, datetime.now()))
            
            conversion_id = cursor.lastrowid
            conn.commit()
            
            return conversion_id
    
    def mark_completed(
        self,
        video_path: Path,
        original_size: int,
        converted_size: int,
        processing_time: float
    ):
        """Mark conversion as completed successfully"""
        space_saved = original_size - converted_size
        compression_ratio = converted_size / original_size if original_size > 0 else 1.0
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE conversions
                SET status = 'completed',
                    converted_size = ?,
                    compression_ratio = ?,
                    space_saved = ?,
                    processing_time = ?,
                    completed_at = ?
                WHERE file_path = ?
                AND status = 'started'
            """, (
                converted_size,
                compression_ratio,
                space_saved,
                processing_time,
                datetime.now(),
                str(video_path)
            ))
            
            # Update statistics
            cursor.execute("""
                UPDATE statistics
                SET successful_conversions = successful_conversions + 1,
                    total_original_size = total_original_size + ?,
                    total_converted_size = total_converted_size + ?,
                    total_space_saved = total_space_saved + ?,
                    total_processing_time = total_processing_time + ?,
                    last_updated = ?
            """, (
                original_size,
                converted_size,
                space_saved,
                processing_time,
                datetime.now()
            ))
            
            conn.commit()
            logger.debug(f"Marked completed: {video_path.name}")
    
    def mark_failed(self, video_path: Path, error_message: str):
        """Mark conversion as failed"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE conversions
                SET status = 'failed',
                    error_message = ?,
                    completed_at = ?
                WHERE file_path = ?
                AND status = 'started'
            """, (error_message, datetime.now(), str(video_path)))
            
            # Update statistics
            cursor.execute("""
                UPDATE statistics
                SET failed_conversions = failed_conversions + 1,
                    last_updated = ?
            """, (datetime.now(),))
            
            conn.commit()
            logger.debug(f"Marked failed: {video_path.name}")
    
    def mark_skipped(self, video_path: Path, reason: str):
        """Mark conversion as skipped"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE conversions
                SET status = 'skipped',
                    error_message = ?,
                    completed_at = ?
                WHERE file_path = ?
                AND status = 'started'
            """, (reason, datetime.now(), str(video_path)))
            
            # Update statistics
            cursor.execute("""
                UPDATE statistics
                SET skipped_conversions = skipped_conversions + 1,
                    last_updated = ?
            """, (datetime.now(),))
            
            conn.commit()
    
    def is_converted(self, video_path: Path) -> bool:
        """Check if video was successfully converted"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM conversions
                WHERE file_path = ?
                AND status = 'completed'
            """, (str(video_path),))
            
            return cursor.fetchone()['count'] > 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get conversion statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM statistics LIMIT 1")
            row = cursor.fetchone()
            
            if not row:
                return {}
            
            stats = dict(row)
            
            # Calculate derived statistics
            if stats['successful_conversions'] > 0:
                stats['avg_savings_percent'] = (
                    stats['total_space_saved'] / stats['total_original_size'] * 100
                    if stats['total_original_size'] > 0 else 0
                )
                stats['avg_compression_ratio'] = (
                    stats['total_converted_size'] / stats['total_original_size']
                    if stats['total_original_size'] > 0 else 1.0
                )
                stats['avg_processing_time'] = (
                    stats['total_processing_time'] / stats['successful_conversions']
                )
            else:
                stats['avg_savings_percent'] = 0
                stats['avg_compression_ratio'] = 1.0
                stats['avg_processing_time'] = 0
            
            return stats
    
    def get_recent_conversions(self, limit: int = 10) -> List[Dict]:
        """Get recent conversion history"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM conversions
                ORDER BY completed_at DESC
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def clear_statistics(self):
        """Reset statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE statistics
                SET successful_conversions = 0,
                    failed_conversions = 0,
                    skipped_conversions = 0,
                    total_original_size = 0,
                    total_converted_size = 0,
                    total_space_saved = 0,
                    total_processing_time = 0,
                    last_updated = ?
            """, (datetime.now(),))
            
            conn.commit()
            logger.info("Statistics cleared")
    
    def close(self):
        """Close database connection"""
        logger.debug("Database closed")