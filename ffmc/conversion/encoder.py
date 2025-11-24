# ffmc/conversion/encoder.py
"""
Video encoder - FFmpeg wrapper
"""

import asyncio
import re
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from ffmc.config.settings import Settings
from ffmc.analysis.codec_detector import VideoAnalysis
from ffmc.conversion.command_builder import CommandBuilder
from ffmc.monitoring.logger import get_logger
from ffmc.utils.exceptions import ConversionError

logger = get_logger('encoder')


@dataclass
class ConversionResult:
    """Result of a video conversion"""
    success: bool
    output_path: Path
    output_size: int
    duration: float
    error_message: Optional[str] = None


class VideoEncoder:
    """
    Handles video encoding using FFmpeg
    
    Features:
    - Progress tracking via FFmpeg output parsing
    - Hardware acceleration support
    - Error handling and validation
    - Post-conversion integrity checking
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.command_builder = CommandBuilder(settings)
    
    async def convert_video(
        self,
        video_path: Path,
        analysis: VideoAnalysis,
        progress_callback: Optional[Callable] = None,
        cpu_affinity: Optional[List[int]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Convert a video file
        
        Args:
            video_path: Input video path
            analysis: Video analysis result
            progress_callback: Optional progress callback
            cpu_affinity: Optional CPU core affinity
            
        Returns:
            Dict with conversion results or None if failed
            
        Raises:
            ConversionError: If conversion fails
        """
        start_time = datetime.now()
        
        # Determine output path
        output_path = self._get_output_path(video_path)
        
        # Build FFmpeg command
        cmd = self.command_builder.build_command(
            input_path=video_path,
            output_path=output_path,
            analysis=analysis,
            cpu_affinity=cpu_affinity
        )
        
        logger.info(f"Converting: {video_path.name}")
        logger.debug(f"Command: {' '.join(cmd)}")
        
        try:
            # Execute FFmpeg
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Monitor progress
            stderr_data = []
            async for line in process.stderr:
                line_str = line.decode('utf-8', errors='ignore')
                stderr_data.append(line_str)
                
                # Parse progress
                if progress_callback:
                    progress = self._parse_progress(line_str, analysis.duration)
                    if progress is not None:
                        progress_callback(
                            video_path.name,
                            progress,
                            completed=False
                        )
            
            await process.wait()
            
            # Check result
            if process.returncode != 0:
                error_msg = ''.join(stderr_data)
                logger.error(f"FFmpeg failed: {error_msg}")
                raise ConversionError(f"FFmpeg error (code {process.returncode})")
            
            if not output_path.exists():
                raise ConversionError("Output file not created")
            
            # Validate output
            output_size = output_path.stat().st_size
            
            if output_size == 0:
                output_path.unlink()
                raise ConversionError("Output file is empty")
            
            # Check if output is larger (skip if enabled)
            if self.settings.skip_if_larger and output_size >= analysis.file_size:
                logger.info(
                    f"Output larger than input, skipping: {video_path.name}"
                )
                output_path.unlink()
                return None
            
            # Handle file replacement
            if not self.settings.output_suffix:
                self._replace_original(video_path, output_path)
            
            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()
            
            # Notify completion
            if progress_callback:
                progress_callback(video_path.name, 100, completed=True)
            
            logger.info(
                f"Conversion complete: {video_path.name} - "
                f"{self._format_size(analysis.file_size)} -> "
                f"{self._format_size(output_size)} "
                f"({self._calculate_savings(analysis.file_size, output_size):.1f}%)"
            )
            
            return {
                'output_path': output_path,
                'output_size': output_size,
                'duration': duration,
                'success': True
            }
            
        except ConversionError:
            raise
        except Exception as e:
            logger.exception(f"Unexpected error during conversion: {e}")
            if output_path.exists():
                output_path.unlink()
            raise ConversionError(f"Conversion failed: {e}")
    
    def _get_output_path(self, video_path: Path) -> Path:
        """Determine output file path"""
        suffix = self.settings.output_suffix
        
        if self.settings.output_directory:
            output_dir = self.settings.output_directory
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = video_path.parent
        
        if suffix:
            output_name = f"{video_path.stem}{suffix}.mp4"
        else:
            output_name = f"{video_path.stem}_temp.mp4"
        
        return output_dir / output_name
    
    def _replace_original(self, original: Path, converted: Path):
        """Replace original file with converted version"""
        if self.settings.create_backup:
            backup_path = original.with_suffix(original.suffix + '.bak')
            original.rename(backup_path)
            logger.debug(f"Created backup: {backup_path.name}")
        else:
            original.unlink()
        
        final_path = original.parent / f"{original.stem}.mp4"
        converted.rename(final_path)
        logger.debug(f"Replaced original: {final_path.name}")
    
    @staticmethod
    def _parse_progress(line: str, duration: float) -> Optional[float]:
        """
        Parse FFmpeg progress from stderr
        
        Args:
            line: FFmpeg output line
            duration: Video duration in seconds
            
        Returns:
            Progress percentage (0-100) or None
        """
        # Match time=HH:MM:SS.MS pattern
        time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
        if time_match and duration > 0:
            hours = int(time_match.group(1))
            minutes = int(time_match.group(2))
            seconds = float(time_match.group(3))
            
            current_time = hours * 3600 + minutes * 60 + seconds
            progress = min(100, (current_time / duration) * 100)
            
            return progress
        
        return None
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    
    @staticmethod
    def _calculate_savings(original: int, converted: int) -> float:
        """Calculate compression savings percentage"""
        if original == 0:
            return 0.0
        return ((original - converted) / original) * 100