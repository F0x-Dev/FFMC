# ffmc/interactive/codec_selector.py
"""
Interactive codec selection interface
Allows user to choose codec based on visual comparison
"""

from typing import List, Optional
from ffmc.analysis.codec_advisor import CodecRecommendation, CodecAdvisor
from ffmc.analysis.codec_detector import VideoAnalysis
from ffmc.monitoring.logger import get_logger

logger = get_logger('interactive')


class InteractiveCodecSelector:
    """Interactive interface for codec selection"""
    
    def __init__(self):
        self.advisor = CodecAdvisor()
    
    def select_codec(
        self,
        analysis: VideoAnalysis,
        gpu_available: Optional[str] = None
    ) -> Optional[CodecRecommendation]:
        """
        Interactive codec selection
        
        Returns:
            Selected codec recommendation or None if cancelled
        """
        print("\n" + "=" * 80)
        print(f"CODEC SELECTION FOR: {analysis.file_path.name}")
        print("=" * 80)
        print(f"Current codec: {analysis.video_codec}")
        print(f"Size: {self._format_size(analysis.file_size)}")
        print(f"Resolution: {analysis.resolution} @ {analysis.fps:.1f} fps")
        print(f"Duration: {self._format_duration(analysis.duration)}")
        print()
        
        # Get recommendations for different quality levels
        print("Select quality preference:")
        print()
        print("1. Maximum Quality   (0-1% loss,   ~40% compression, slow)")
        print("2. High Quality      (1-3% loss,   ~50% compression, medium)")
        print("3. Balanced          (3-5% loss,   ~60% compression, fast)")
        print("4. High Compression  (5-10% loss,  ~70% compression, very fast)")
        print("5. Show All Options")
        print("0. Cancel")
        print()
        
        choice = input("Enter choice [1-5, 0 to cancel]: ").strip()
        
        if choice == "0":
            return None
        
        if choice == "5":
            return self._show_all_options(analysis, gpu_available)
        
        # Map choice to quality constraints
        quality_map = {
            "1": (1.0, 0.4),   # max_loss, min_compression
            "2": (3.0, 0.5),
            "3": (5.0, 0.6),
            "4": (10.0, 0.7),
        }
        
        if choice in quality_map:
            max_loss, min_comp = quality_map[choice]
            recommendations = self.advisor.analyze_and_recommend(
                analysis,
                max_quality_loss=max_loss,
                min_compression=min_comp,
                gpu_available=gpu_available
            )
            
            if not recommendations:
                print("\nNo codecs match these criteria.")
                return None
            
            return self._select_from_recommendations(recommendations)
        
        print("Invalid choice.")
        return None
    
    def _show_all_options(
        self,
        analysis: VideoAnalysis,
        gpu_available: Optional[str]
    ) -> Optional[CodecRecommendation]:
        """Show all available codec options"""
        recommendations = self.advisor.analyze_and_recommend(
            analysis,
            max_quality_loss=100.0,  # No limit
            min_compression=0.0,      # No limit
            gpu_available=gpu_available
        )
        
        return self._select_from_recommendations(recommendations)
    
    def _select_from_recommendations(
        self,
        recommendations: List[CodecRecommendation]
    ) -> Optional[CodecRecommendation]:
        """Display recommendations and let user choose"""
        print("\n" + "=" * 80)
        print("AVAILABLE CODECS")
        print("=" * 80)
        
        for i, rec in enumerate(recommendations, 1):
            print(f"\n{i}. {rec.display_name}")
            print(f"   Quality: {self._get_quality_bar(rec.estimated_quality_loss)} "
                  f"({rec.estimated_quality_loss:.1f}% loss, VMAF ~{rec.vmaf_score_estimate:.0f})")
            print(f"   Size:    {self._get_compression_bar(rec.space_saved_percent)} "
                  f"({self._format_size(rec.estimated_size)}, saves {rec.space_saved_percent:.0f}%)")
            print(f"   Speed:   {self._get_speed_bar(rec.encoding_speed)} "
                  f"({rec.encoding_speed}, ~{self._format_duration(rec.estimated_time)})")
            if rec.requires_gpu:
                print(f"   GPU:     Required ({rec.gpu_type.upper()})")
            print(f"   Score:   {rec.overall_score:.1f}/100")
        
        print(f"\n0. Cancel")
        print("=" * 80)
        
        while True:
            choice = input(f"\nSelect codec [1-{len(recommendations)}, 0 to cancel]: ").strip()
            
            if choice == "0":
                return None
            
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(recommendations):
                    selected = recommendations[idx]
                    
                    # Confirm selection
                    print(f"\nSelected: {selected.display_name}")
                    print(f"Quality loss: {selected.estimated_quality_loss:.1f}%")
                    print(f"Output size: {self._format_size(selected.estimated_size)}")
                    print(f"Encoding time: ~{self._format_duration(selected.estimated_time)}")
                    
                    confirm = input("\nProceed with this codec? [Y/n]: ").strip().lower()
                    if confirm in ['', 'y', 'yes']:
                        return selected
                    else:
                        print("Selection cancelled.")
                        return None
            except ValueError:
                pass
            
            print("Invalid choice. Try again.")
    
    def _get_quality_bar(self, quality_loss: float) -> str:
        """Visual bar for quality (inverse - lower loss is better)"""
        quality_score = max(0, 100 - quality_loss * 10)
        bars = int(quality_score / 10)
        return "█" * bars + "░" * (10 - bars)
    
    def _get_compression_bar(self, compression_percent: float) -> str:
        """Visual bar for compression"""
        bars = int(compression_percent / 10)
        return "█" * bars + "░" * (10 - bars)
    
    def _get_speed_bar(self, speed: str) -> str:
        """Visual bar for encoding speed"""
        speed_map = {
            "very slow": 2,
            "slow": 4,
            "medium": 6,
            "fast": 8,
            "very fast": 10
        }
        bars = speed_map.get(speed, 5)
        return "█" * bars + "░" * (10 - bars)
    
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
            return f"{h}h{m}m"
        elif m > 0:
            return f"{m}m{s}s"
        else:
            return f"{s}s"


# =============================================================================
# ESEMPIO DI UTILIZZO NEL CLI
# =============================================================================

"""
# Aggiungi al cli.py:

parser.add_argument(
    "--interactive",
    action="store_true",
    help="Interactive codec selection mode"
)

# Nel async_main():

if args.interactive:
    from ffmc.interactive.codec_selector import InteractiveCodecSelector
    from ffmc.analysis.codec_detector import CodecDetector
    
    selector = InteractiveCodecSelector()
    detector = CodecDetector(settings)
    
    for path in args.paths:
        if path.is_file():
            analysis = await detector.analyze_video(path)
            if analysis:
                gpu = settings.hardware_acceleration.type if settings.hardware_acceleration.enabled else None
                selected_codec = selector.select_codec(analysis, gpu)
                
                if selected_codec:
                    print(f"\n✓ Selected: {selected_codec.display_name}")
                    # Apply selected codec settings to settings object
                    settings.target_video_codec = selected_codec.codec_name
                    settings.video_quality.crf = selected_codec.settings.get('crf', 23)
                    settings.video_quality.preset = selected_codec.settings.get('preset', 'medium')
                    
                    # Continue with conversion...
                    print(f"Starting conversion with {selected_codec.display_name}...")
                    # ... (normal conversion flow)
                else:
                    print("Codec selection cancelled.")
                    return 0

# ESEMPIO OUTPUT:
# ================================================================================
# CODEC SELECTION FOR: Driver.mp4
# ================================================================================
# Current codec: h264
# Size: 332.0 MB
# Resolution: 720x404 @ 25.0 fps
# Duration: 42m 15s
#
# Select quality preference:
#
# 1. Maximum Quality   (0-1% loss,   ~40% compression, slow)
# 2. High Quality      (1-3% loss,   ~50% compression, medium)
# 3. Balanced          (3-5% loss,   ~60% compression, fast)
# 4. High Compression  (5-10% loss,  ~70% compression, very fast)
# 5. Show All Options
# 0. Cancel
#
# Enter choice [1-5, 0 to cancel]: 5
#
# ================================================================================
# AVAILABLE CODECS
# ================================================================================
#
# 1. H.265 High Quality
#    Quality: ██████████ (0.5% loss, VMAF ~98)
#    Size:    █████░░░░░ (166.0 MB, saves 50%)
#    Speed:   ████░░░░░░ (slow, ~21m)
#    Score:   92.3/100
#
# 2. H.265 Balanced
#    Quality: ████████░░ (2.0% loss, VMAF ~95)
#    Size:    ██████░░░░ (132.8 MB, saves 60%)
#    Speed:   ██████░░░░ (medium, ~14m)
#    Score:   89.5/100
#
# 3. H.265 GPU (NVIDIA)
#    Quality: ███████░░░ (3.0% loss, VMAF ~93)
#    Size:    █████░░░░░ (149.4 MB, saves 55%)
#    Speed:   ██████████ (very fast, ~2m)
#    GPU:     Required (NVIDIA)
#    Score:   87.1/100
#
# 0. Cancel
# ================================================================================
#
# Select codec [1-3, 0 to cancel]: 2
#
# Selected: H.265 Balanced
# Quality loss: 2.0%
# Output size: 132.8 MB
# Encoding time: ~14m
#
# Proceed with this codec? [Y/n]: y
#
# ✓ Selected: H.265 Balanced
# Starting conversion with H.265 Balanced...
"""