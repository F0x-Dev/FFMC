# ffmc/analysis/codec_advisor.py
"""
Intelligent codec selection with quality prediction
Analyzes video and recommends optimal codecs with quality/size trade-offs
"""

from dataclasses import dataclass
from typing import List, Dict, Any
from enum import Enum
from pathlib import Path

from ffmc.analysis.codec_detector import VideoAnalysis
from ffmc.monitoring.logger import get_logger

logger = get_logger('codec_advisor')


class QualityLevel(Enum):
    """Quality levels for codec recommendations"""
    LOSSLESS = "lossless"
    MINIMAL_LOSS = "minimal"      # <1% quality loss, ~40% size reduction
    LOW_LOSS = "low"               # 1-3% quality loss, ~50% size reduction
    MODERATE_LOSS = "moderate"     # 3-5% quality loss, ~60% size reduction
    HIGH_LOSS = "high"             # 5-10% quality loss, ~70% size reduction
    EXTREME = "extreme"            # >10% quality loss, ~80% size reduction


@dataclass
class CodecRecommendation:
    """Recommendation for a specific codec configuration"""
    codec_name: str
    display_name: str
    
    # Quality metrics
    quality_level: QualityLevel
    estimated_quality_loss: float  # 0-100 scale (0 = lossless, 100 = terrible)
    vmaf_score_estimate: float     # 0-100 (higher = better)
    
    # Size metrics
    estimated_size: int            # bytes
    estimated_compression: float   # 0-1 ratio
    space_saved: int              # bytes
    space_saved_percent: float    # percentage
    
    # Performance
    encoding_speed: str           # "very slow", "slow", "medium", "fast", "very fast"
    estimated_time: float         # seconds
    
    # Requirements
    requires_gpu: bool
    gpu_type: str                 # "nvidia", "amd", "intel", "none"
    
    # Encoding settings
    settings: Dict[str, Any]
    
    # Score (higher = better overall)
    overall_score: float          # 0-100 weighted score
    
    def __str__(self):
        return (
            f"{self.display_name}\n"
            f"  Quality Loss: {self.estimated_quality_loss:.1f}% "
            f"(VMAF ~{self.vmaf_score_estimate:.0f})\n"
            f"  Size: {self._format_size(self.estimated_size)} "
            f"(saves {self.space_saved_percent:.1f}%)\n"
            f"  Speed: {self.encoding_speed}\n"
            f"  GPU: {self.gpu_type if self.requires_gpu else 'Not required'}"
        )
    
    @staticmethod
    def _format_size(bytes: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024
        return f"{bytes:.1f} TB"


class CodecAdvisor:
    """
    Analyzes video and recommends optimal codecs
    
    Provides multiple recommendations ranked by:
    - Quality preservation
    - Compression ratio
    - Encoding speed
    - Hardware requirements
    """
    
    def __init__(self):
        self.codec_profiles = self._initialize_codec_profiles()
    
    def _initialize_codec_profiles(self) -> Dict[str, Dict]:
        """Initialize codec profiles with characteristics"""
        return {
            # H.265/HEVC variants
            "hevc_quality": {
                "codec": "hevc",
                "display_name": "H.265 High Quality",
                "crf": 18,
                "preset": "slow",
                "compression_ratio": 0.5,
                "quality_loss": 0.5,
                "vmaf_estimate": 98,
                "speed_factor": 0.3,
                "quality_level": QualityLevel.MINIMAL_LOSS,
            },
            "hevc_balanced": {
                "codec": "hevc",
                "display_name": "H.265 Balanced",
                "crf": 23,
                "preset": "medium",
                "compression_ratio": 0.4,
                "quality_loss": 2.0,
                "vmaf_estimate": 95,
                "speed_factor": 1.0,
                "quality_level": QualityLevel.LOW_LOSS,
            },
            "hevc_fast": {
                "codec": "hevc",
                "display_name": "H.265 Fast",
                "crf": 28,
                "preset": "fast",
                "compression_ratio": 0.3,
                "quality_loss": 5.0,
                "vmaf_estimate": 90,
                "speed_factor": 2.0,
                "quality_level": QualityLevel.MODERATE_LOSS,
            },
            
            # AV1 variants
            "av1_quality": {
                "codec": "av1",
                "display_name": "AV1 High Quality",
                "crf": 25,
                "preset": "4",
                "compression_ratio": 0.35,
                "quality_loss": 1.0,
                "vmaf_estimate": 97,
                "speed_factor": 0.1,  # Very slow
                "quality_level": QualityLevel.MINIMAL_LOSS,
            },
            "av1_balanced": {
                "codec": "av1",
                "display_name": "AV1 Balanced",
                "crf": 30,
                "preset": "6",
                "compression_ratio": 0.28,
                "quality_loss": 3.0,
                "vmaf_estimate": 93,
                "speed_factor": 0.3,
                "quality_level": QualityLevel.LOW_LOSS,
            },
            
            # H.264 (for compatibility)
            "h264_quality": {
                "codec": "h264",
                "display_name": "H.264 High Quality",
                "crf": 18,
                "preset": "slow",
                "compression_ratio": 0.6,
                "quality_loss": 0.5,
                "vmaf_estimate": 98,
                "speed_factor": 0.5,
                "quality_level": QualityLevel.MINIMAL_LOSS,
            },
            "h264_balanced": {
                "codec": "h264",
                "display_name": "H.264 Balanced",
                "crf": 23,
                "preset": "medium",
                "compression_ratio": 0.5,
                "quality_loss": 2.0,
                "vmaf_estimate": 95,
                "speed_factor": 1.5,
                "quality_level": QualityLevel.LOW_LOSS,
            },
            
            # VP9
            "vp9_quality": {
                "codec": "vp9",
                "display_name": "VP9 High Quality",
                "crf": 25,
                "preset": "2",
                "compression_ratio": 0.4,
                "quality_loss": 1.5,
                "vmaf_estimate": 96,
                "speed_factor": 0.2,
                "quality_level": QualityLevel.MINIMAL_LOSS,
            },
            
            # GPU accelerated variants
            "hevc_nvenc": {
                "codec": "hevc_nvenc",
                "display_name": "H.265 GPU (NVIDIA)",
                "cq": 23,
                "preset": "p4",
                "compression_ratio": 0.45,
                "quality_loss": 3.0,
                "vmaf_estimate": 93,
                "speed_factor": 5.0,  # Very fast
                "quality_level": QualityLevel.LOW_LOSS,
                "gpu": "nvidia",
            },
            "hevc_amf": {
                "codec": "hevc_amf",
                "display_name": "H.265 GPU (AMD)",
                "cq": 23,
                "preset": "quality",
                "compression_ratio": 0.45,
                "quality_loss": 3.5,
                "vmaf_estimate": 92,
                "speed_factor": 5.0,
                "quality_level": QualityLevel.LOW_LOSS,
                "gpu": "amd",
            },
        }
    
    def analyze_and_recommend(
        self,
        analysis: VideoAnalysis,
        max_quality_loss: float = 5.0,
        min_compression: float = 0.3,
        gpu_available: str = None
    ) -> List[CodecRecommendation]:
        """
        Analyze video and provide codec recommendations
        
        Args:
            analysis: Video analysis result
            max_quality_loss: Maximum acceptable quality loss (%)
            min_compression: Minimum compression ratio (0-1)
            gpu_available: GPU type if available ("nvidia", "amd", "intel", None)
            
        Returns:
            List of recommendations sorted by overall score
        """
        recommendations = []
        
        for profile_name, profile in self.codec_profiles.items():
            # Skip GPU codecs if no GPU
            if profile.get("gpu") and not gpu_available:
                continue
            
            # Skip if GPU type doesn't match
            if profile.get("gpu") and profile["gpu"] != gpu_available:
                continue
            
            # Skip if quality loss too high
            if profile["quality_loss"] > max_quality_loss:
                continue
            
            # Skip if compression too low
            if profile["compression_ratio"] > (1 - min_compression):
                continue
            
            # Calculate metrics
            recommendation = self._create_recommendation(
                profile, analysis, gpu_available
            )
            
            recommendations.append(recommendation)
        
        # Sort by overall score
        recommendations.sort(key=lambda r: r.overall_score, reverse=True)
        
        return recommendations
    
    def _create_recommendation(
        self,
        profile: Dict,
        analysis: VideoAnalysis,
        gpu_available: str
    ) -> CodecRecommendation:
        """Create a codec recommendation from profile"""
        
        # Calculate estimated size
        estimated_size = int(analysis.file_size * profile["compression_ratio"])
        space_saved = analysis.file_size - estimated_size
        space_saved_percent = (space_saved / analysis.file_size) * 100
        
        # Estimate encoding time
        base_time = analysis.duration  # 1x realtime baseline
        speed_factor = profile["speed_factor"]
        estimated_time = base_time / speed_factor
        
        # Adjust quality loss based on content
        quality_loss = self._adjust_quality_for_content(
            profile["quality_loss"],
            analysis
        )
        
        # Calculate overall score (weighted)
        overall_score = self._calculate_overall_score(
            compression=1 - profile["compression_ratio"],
            quality_loss=quality_loss,
            speed=speed_factor,
            vmaf=profile["vmaf_estimate"]
        )
        
        # Encoding speed label
        speed_label = self._get_speed_label(speed_factor)
        
        return CodecRecommendation(
            codec_name=profile["codec"],
            display_name=profile["display_name"],
            quality_level=profile["quality_level"],
            estimated_quality_loss=quality_loss,
            vmaf_score_estimate=profile["vmaf_estimate"],
            estimated_size=estimated_size,
            estimated_compression=profile["compression_ratio"],
            space_saved=space_saved,
            space_saved_percent=space_saved_percent,
            encoding_speed=speed_label,
            estimated_time=estimated_time,
            requires_gpu=bool(profile.get("gpu")),
            gpu_type=profile.get("gpu", "none"),
            settings=self._extract_settings(profile),
            overall_score=overall_score
        )
    
    def _adjust_quality_for_content(
        self,
        base_quality_loss: float,
        analysis: VideoAnalysis
    ) -> float:
        """Adjust quality loss estimate based on content"""
        adjusted = base_quality_loss
        
        # High resolution content compresses better
        if analysis.width >= 1920:
            adjusted *= 0.9
        
        # High bitrate content has more room for compression
        if analysis.bitrate > 5_000_000:  # 5 Mbps
            adjusted *= 0.85
        
        # Low FPS content easier to compress
        if analysis.fps <= 24:
            adjusted *= 0.95
        
        return adjusted
    
    def _calculate_overall_score(
        self,
        compression: float,
        quality_loss: float,
        speed: float,
        vmaf: float
    ) -> float:
        """
        Calculate weighted overall score
        
        Weights:
        - Quality: 40%
        - Compression: 35%
        - Speed: 15%
        - VMAF: 10%
        """
        quality_score = max(0, 100 - quality_loss * 10)  # Penalize quality loss
        compression_score = compression * 100
        speed_score = min(100, speed * 20)
        vmaf_score = vmaf
        
        overall = (
            quality_score * 0.40 +
            compression_score * 0.35 +
            speed_score * 0.15 +
            vmaf_score * 0.10
        )
        
        return overall
    
    def _get_speed_label(self, speed_factor: float) -> str:
        """Convert speed factor to human readable label"""
        if speed_factor < 0.2:
            return "very slow"
        elif speed_factor < 0.5:
            return "slow"
        elif speed_factor < 1.5:
            return "medium"
        elif speed_factor < 3.0:
            return "fast"
        else:
            return "very fast"
    
    def _extract_settings(self, profile: Dict) -> Dict[str, Any]:
        """Extract encoding settings from profile"""
        settings = {}
        
        if "crf" in profile:
            settings["crf"] = profile["crf"]
        if "cq" in profile:
            settings["cq"] = profile["cq"]
        if "preset" in profile:
            settings["preset"] = profile["preset"]
        
        return settings
    
    def print_recommendations(
        self,
        recommendations: List[CodecRecommendation],
        analysis: VideoAnalysis
    ):
        """Print formatted recommendations"""
        logger.info("=" * 80)
        logger.info(f"CODEC RECOMMENDATIONS FOR: {analysis.file_path.name}")
        logger.info("=" * 80)
        logger.info(f"Current: {analysis.video_codec}")
        logger.info(f"Size: {self._format_size(analysis.file_size)}")
        logger.info(f"Resolution: {analysis.resolution} @ {analysis.fps:.1f} fps")
        logger.info(f"Duration: {self._format_duration(analysis.duration)}")
        logger.info("")
        
        for i, rec in enumerate(recommendations, 1):
            logger.info(f"{i}. {rec.display_name}")
            logger.info(f"   Quality Loss: {rec.estimated_quality_loss:.1f}% "
                       f"(VMAF ~{rec.vmaf_score_estimate:.0f}/100)")
            logger.info(f"   Output Size: {self._format_size(rec.estimated_size)} "
                       f"(-{rec.space_saved_percent:.1f}%)")
            logger.info(f"   Encoding Speed: {rec.encoding_speed} "
                       f"(~{self._format_duration(rec.estimated_time)})")
            if rec.requires_gpu:
                logger.info(f"   Requires: {rec.gpu_type.upper()} GPU")
            logger.info(f"   Overall Score: {rec.overall_score:.1f}/100")
            logger.info("")
        
        logger.info("=" * 80)
    
    @staticmethod
    def _format_size(bytes: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024
        return f"{bytes:.1f} TB"
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        
        if h > 0:
            return f"{h}h {m}m"
        elif m > 0:
            return f"{m}m {s}s"
        else:
            return f"{s}s"