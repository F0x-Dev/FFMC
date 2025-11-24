# ffmc/conversion/command_builder.py
"""
FFmpeg command builder with hardware acceleration support
Constructs optimized FFmpeg commands for video conversion
"""

from pathlib import Path
from typing import List, Optional, Dict, Any
import psutil

from ffmc.config.settings import Settings
from ffmc.analysis.codec_detector import VideoAnalysis
from ffmc.monitoring.logger import get_logger

logger = get_logger('command_builder')


class CommandBuilder:
    """
    Builds optimized FFmpeg commands for video conversion
    
    Supports:
    - Software encoding (libx265)
    - Hardware acceleration (NVENC, AMF, QSV, VideoToolbox)
    - Quality presets and tuning
    - Audio transcoding
    - CPU thread optimization
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.hw_accel = settings.hardware_acceleration
    
    def build_command(
        self,
        input_path: Path,
        output_path: Path,
        analysis: VideoAnalysis,
        cpu_affinity: Optional[List[int]] = None
    ) -> List[str]:
        """
        Build complete FFmpeg command
        
        Args:
            input_path: Source video file
            output_path: Destination file
            analysis: Video analysis result
            cpu_affinity: Optional CPU core affinity
            
        Returns:
            List of command arguments
        """
        cmd = [self.settings.ffmpeg_path]
        
        # Global options
        cmd.extend(self._build_global_options(cpu_affinity))
        
        # Hardware acceleration (input)
        if self.hw_accel.enabled:
            cmd.extend(self._build_hw_decode_options())
        
        # Input file
        cmd.extend(['-i', str(input_path)])
        
        # Video encoding
        cmd.extend(self._build_video_options(analysis))
        
        # Audio encoding
        cmd.extend(self._build_audio_options(analysis))
        
        # Output options
        cmd.extend(self._build_output_options())
        
        # Output file
        cmd.extend(['-y', str(output_path)])
        
        logger.debug(f"Built command: {' '.join(cmd)}")
        return cmd
    
    def _build_global_options(
        self,
        cpu_affinity: Optional[List[int]] = None
    ) -> List[str]:
        """Build global FFmpeg options"""
        options = []
        
        # Thread count optimization
        if self.hw_accel.enabled:
            # Minimal threads for hardware encoding
            threads = 2
        else:
            # Optimize for software encoding
            if cpu_affinity:
                threads = len(cpu_affinity)
            else:
                threads = min(4, psutil.cpu_count(logical=False) or 2)
        
        options.extend(['-threads', str(threads)])
        
        # Hide banner and reduce log verbosity
        options.extend(['-hide_banner', '-loglevel', 'warning', '-stats'])
        
        return options
    
    def _build_hw_decode_options(self) -> List[str]:
        """Build hardware acceleration decode options"""
        options = []
        
        hw_type = self.hw_accel.type.lower()
        
        if hw_type == 'nvidia':
            options.extend(['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda'])
        elif hw_type == 'amd':
            options.extend(['-hwaccel', 'vulkan'])
        elif hw_type == 'intel':
            options.extend(['-hwaccel', 'qsv'])
        elif hw_type == 'videotoolbox':
            options.extend(['-hwaccel', 'videotoolbox'])
        else:
            options.extend(['-hwaccel', 'auto'])
        
        return options
    
    def _build_video_options(self, analysis: VideoAnalysis) -> List[str]:
        """Build video encoding options"""
        options = []
        
        if self.hw_accel.enabled:
            options.extend(self._build_hw_encode_options(analysis))
        else:
            options.extend(self._build_sw_encode_options(analysis))
        
        # Pixel format
        options.extend(['-pix_fmt', 'yuv420p'])
        
        # Copy subtitle streams if present
        options.extend(['-c:s', 'copy'])
        
        return options
    
    def _build_hw_encode_options(self, analysis: VideoAnalysis) -> List[str]:
        """Build hardware encoding options"""
        options = []
        encoder = self.hw_accel.encoder
        
        options.extend(['-c:v', encoder])
        
        # Quality control for hardware encoders
        hw_type = self.hw_accel.type.lower()
        
        if hw_type == 'nvidia':
            # NVENC options
            options.extend([
                '-preset', 'p4',  # Quality preset
                '-tune', 'hq',    # High quality tuning
                '-rc', 'vbr',     # Variable bitrate
                '-cq', str(self.settings.video_quality.crf),
                '-b:v', '0',      # No bitrate limit
                '-spatial-aq', '1',
                '-temporal-aq', '1'
            ])
        elif hw_type == 'amd':
            # AMF options
            options.extend([
                '-quality', 'quality',
                '-rc', 'vbr_latency',
                '-qp_i', str(self.settings.video_quality.crf),
                '-qp_p', str(self.settings.video_quality.crf + 2)
            ])
        elif hw_type == 'intel':
            # QSV options
            options.extend([
                '-preset', 'veryslow',
                '-global_quality', str(self.settings.video_quality.crf)
            ])
        elif hw_type == 'videotoolbox':
            # VideoToolbox options
            options.extend([
                '-q:v', str(self.settings.video_quality.crf * 2)
            ])
        
        return options
    
    def _build_sw_encode_options(self, analysis: VideoAnalysis) -> List[str]:
        """Build software encoding options (libx265)"""
        options = []
        
        options.extend(['-c:v', 'libx265'])
        
        # Quality settings
        vq = self.settings.video_quality
        options.extend([
            '-crf', str(vq.crf),
            '-preset', vq.preset
        ])
        
        if vq.tune:
            options.extend(['-tune', vq.tune])
        
        # x265 parameters for optimal quality/speed
        x265_params = [
            'log-level=error',
            'aq-mode=3',
            'no-sao=1'
        ]
        
        # Adaptive quantization
        if analysis.width >= 1920:
            x265_params.append('aq-strength=1.0')
        
        # HDR passthrough if detected
        if 'hdr' in str(analysis.probe_data).lower():
            x265_params.extend([
                'hdr-opt=1',
                'repeat-headers=1',
                'colorprim=bt2020',
                'transfer=smpte2084',
                'colormatrix=bt2020nc'
            ])
        
        options.extend(['-x265-params', ':'.join(x265_params)])
        
        return options
    
    def _build_audio_options(self, analysis: VideoAnalysis) -> List[str]:
        """Build audio encoding options"""
        options = []
        
        if analysis.audio_codec == 'none':
            # No audio stream
            options.extend(['-an'])
        elif analysis.audio_codec == self.settings.target_audio_codec:
            # Audio already in target format, copy
            options.extend(['-c:a', 'copy'])
        else:
            # Transcode audio
            options.extend([
                '-c:a', self.settings.target_audio_codec,
                '-b:a', self.settings.audio_quality.bitrate,
                '-ac', '2'  # Stereo
            ])
        
        return options
    
    def _build_output_options(self) -> List[str]:
        """Build output container options"""
        options = []
        
        # MP4 optimization
        options.extend([
            '-movflags', '+faststart',  # Enable streaming
            '-f', 'mp4'
        ])
        
        return options
    
    def estimate_output_size(
        self,
        analysis: VideoAnalysis
    ) -> int:
        """
        Estimate output file size
        
        Args:
            analysis: Video analysis
            
        Returns:
            Estimated size in bytes
        """
        duration = analysis.duration
        
        # Calculate video bitrate
        if self.hw_accel.enabled:
            # Hardware encoding typically less efficient
            compression_factor = 0.7
        else:
            # Software encoding (libx265) compression
            crf = self.settings.video_quality.crf
            if crf <= 20:
                compression_factor = 0.5
            elif crf <= 23:
                compression_factor = 0.4
            elif crf <= 28:
                compression_factor = 0.3
            else:
                compression_factor = 0.25
        
        estimated_video_size = int(analysis.file_size * compression_factor)
        
        # Add audio size (usually minimal)
        audio_bitrate = int(
            self.settings.audio_quality.bitrate.rstrip('k')
        ) * 1000
        estimated_audio_size = int((audio_bitrate * duration) / 8)
        
        # Add 5% overhead for container
        total_estimate = int((estimated_video_size + estimated_audio_size) * 1.05)
        
        return total_estimate
    
    def get_encoder_info(self) -> Dict[str, Any]:
        """Get information about the configured encoder"""
        info = {
            'mode': 'hardware' if self.hw_accel.enabled else 'software',
            'video_codec': self.settings.target_video_codec,
            'audio_codec': self.settings.target_audio_codec
        }
        
        if self.hw_accel.enabled:
            info.update({
                'hw_type': self.hw_accel.type,
                'encoder': self.hw_accel.encoder
            })
        else:
            info.update({
                'crf': self.settings.video_quality.crf,
                'preset': self.settings.video_quality.preset,
                'tune': self.settings.video_quality.tune
            })
        
        return info