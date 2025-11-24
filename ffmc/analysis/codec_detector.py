"""
Video codec detection and analysis
"""

import asyncio
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from ffmc.config.settings import Settings
from ffmc.monitoring.logger import get_logger
from ffmc.utils.exceptions import AnalysisError

logger = get_logger('codec_detector')


@dataclass
class VideoAnalysis:
    """Video analysis result"""
    file_path: Path
    
    # Codec information
    video_codec: str
    audio_codec: str
    container: str
    
    # Video properties
    resolution: str
    width: int
    height: int
    fps: float
    duration: float
    bitrate: int
    
    # File properties
    file_size: int
    
    # Conversion decision
    needs_conversion: bool
    reason: str
    
    # Raw probe data (for advanced analysis)
    probe_data: dict
    
    def __str__(self):
        return (
            f"VideoAnalysis(file={self.file_path.name}, "
            f"codec={self.video_codec}, "
            f"resolution={self.resolution}, "
            f"needs_conversion={self.needs_conversion})"
        )


class CodecDetector:
    """
    Analyzes video files to determine codec and conversion needs
    
    Uses ffprobe to extract video metadata and determine if conversion
    is necessary based on target codec settings.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.target_video_codec = settings.target_video_codec
        self.target_audio_codec = settings.target_audio_codec
        self.ffprobe_path = settings.ffprobe_path
    
    async def analyze_video(self, video_path: Path) -> Optional[VideoAnalysis]:
        """
        Analyze a video file and determine if conversion is needed
        
        Args:
            video_path: Path to video file
            
        Returns:
            VideoAnalysis object or None if analysis fails
            
        Raises:
            AnalysisError: If ffprobe fails or video is invalid
        """
        logger.debug(f"Analyzing: {video_path.name}")
        
        try:
            # Run ffprobe
            probe_data = await self._run_ffprobe(video_path)
            
            # Extract streams
            video_stream = self._find_video_stream(probe_data)
            audio_stream = self._find_audio_stream(probe_data)
            format_info = probe_data.get('format', {})
            
            if not video_stream:
                raise AnalysisError(f"No video stream found in {video_path.name}")
            
            # Extract codec information
            video_codec = video_stream.get('codec_name', 'unknown').lower()
            audio_codec = audio_stream.get('codec_name', 'none').lower() if audio_stream else 'none'
            container = format_info.get('format_name', 'unknown').split(',')[0]
            
            # Extract video properties
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))
            resolution = f"{width}x{height}"
            
            fps = self._calculate_fps(video_stream)
            duration = float(format_info.get('duration', 0))
            bitrate = int(format_info.get('bit_rate', 0))
            file_size = video_path.stat().st_size
            
            # Determine if conversion is needed
            needs_conversion, reason = self._needs_conversion(
                video_codec,
                audio_codec,
                container,
                bitrate,
                width,
                height
            )
            
            analysis = VideoAnalysis(
                file_path=video_path,
                video_codec=video_codec,
                audio_codec=audio_codec,
                container=container,
                resolution=resolution,
                width=width,
                height=height,
                fps=fps,
                duration=duration,
                bitrate=bitrate,
                file_size=file_size,
                needs_conversion=needs_conversion,
                reason=reason,
                probe_data=probe_data
            )
            
            logger.debug(f"Analysis complete: {video_path.name} - {reason}")
            return analysis
            
        except AnalysisError:
            raise
        except Exception as e:
            logger.error(f"Failed to analyze {video_path.name}: {e}", exc_info=True)
            raise AnalysisError(f"Analysis failed: {e}") from e
    
    async def _run_ffprobe(self, video_path: Path) -> dict:
        """Run ffprobe and return JSON output"""
        cmd = [
            self.ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            '-show_error',
            str(video_path)
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                raise AnalysisError(
                    f"ffprobe failed with code {process.returncode}: {error_msg}"
                )
            
            return json.loads(stdout.decode('utf-8'))
            
        except json.JSONDecodeError as e:
            raise AnalysisError(f"Failed to parse ffprobe output: {e}")
        except Exception as e:
            raise AnalysisError(f"ffprobe execution failed: {e}")
    
    @staticmethod
    def _find_video_stream(probe_data: dict) -> Optional[dict]:
        """Find the primary video stream"""
        streams = probe_data.get('streams', [])
        for stream in streams:
            if stream.get('codec_type') == 'video':
                # Skip cover art and thumbnail streams
                disposition = stream.get('disposition', {})
                if not disposition.get('attached_pic', 0):
                    return stream
        return None
    
    @staticmethod
    def _find_audio_stream(probe_data: dict) -> Optional[dict]:
        """Find the primary audio stream"""
        streams = probe_data.get('streams', [])
        for stream in streams:
            if stream.get('codec_type') == 'audio':
                return stream
        return None
    
    @staticmethod
    def _calculate_fps(video_stream: dict) -> float:
        """Calculate FPS from video stream"""
        # Try r_frame_rate first (more accurate)
        r_frame_rate = video_stream.get('r_frame_rate', '0/1')
        if '/' in r_frame_rate:
            num, den = map(int, r_frame_rate.split('/'))
            if den != 0:
                return num / den
        
        # Fallback to avg_frame_rate
        avg_frame_rate = video_stream.get('avg_frame_rate', '0/1')
        if '/' in avg_frame_rate:
            num, den = map(int, avg_frame_rate.split('/'))
            if den != 0:
                return num / den
        
        return 30.0  # Default fallback
    
    def _needs_conversion(
        self,
        video_codec: str,
        audio_codec: str,
        container: str,
        bitrate: int,
        width: int,
        height: int
    ) -> tuple[bool, str]:
        """
        Determine if video needs conversion
        
        Returns:
            (needs_conversion, reason)
        """
        reasons = []
        
        # Check video codec
        if video_codec != self.target_video_codec:
            reasons.append(f"video codec: {video_codec} -> {self.target_video_codec}")
        
        # Check audio codec
        if audio_codec not in [self.target_audio_codec, 'none']:
            reasons.append(f"audio codec: {audio_codec} -> {self.target_audio_codec}")
        
        # Check if bitrate is excessive (optional optimization)
        if bitrate > 0:
            optimal_bitrate = self._calculate_optimal_bitrate(width, height)
            if bitrate > optimal_bitrate * 1.5:  # 50% over optimal
                reasons.append(f"excessive bitrate: {bitrate//1000}k -> {optimal_bitrate//1000}k")
        
        if reasons:
            return True, ", ".join(reasons)
        else:
            return False, "already optimal"
    
    def _calculate_optimal_bitrate(self, width: int, height: int) -> int:
        """Calculate optimal bitrate for H.265 based on resolution"""
        pixels = width * height
        
        # Bitrate guidelines for H.265
        if pixels <= 921600:  # 720p (1280x720)
            return 1500 * 1000  # 1.5 Mbps
        elif pixels <= 2073600:  # 1080p (1920x1080)
            return 3000 * 1000  # 3 Mbps
        elif pixels <= 8294400:  # 4K (3840x2160)
            return 8000 * 1000  # 8 Mbps
        else:  # 8K and above
            return 20000 * 1000  # 20 Mbps