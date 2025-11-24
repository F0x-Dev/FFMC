# ffmc/cli.py - FIXED VERSION
"""
Command-line interface for FFMC
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from ffmc.core.orchestrator import ConversionOrchestrator
from ffmc.config.settings import Settings
from ffmc.monitoring.logger import setup_logging
from ffmc.utils.exceptions import FFMCError


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser"""
    parser = argparse.ArgumentParser(
        prog="ffmc",
        description="FFMC - Professional video conversion tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ffmc /path/to/videos                      # Convert with default settings
  ffmc /path/to/videos --profile fast       # Fast conversion
  ffmc /path/to/videos --dry-run            # Preview only
  ffmc --config custom.yaml /path/to/videos # Custom config
  ffmc --resume                             # Resume previous job
        """
    )
    
    # Positional arguments
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Paths to scan for videos"
    )
    
    # Configuration
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=None,
        help="Path to configuration file"
    )
    
    parser.add_argument(
        "-p", "--profile",
        choices=["fast", "balanced", "quality", "archive"],
        default="balanced",
        help="Conversion profile (default: balanced)"
    )
    
    # Operation modes
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview conversions without executing"
    )
    
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume previous conversion job"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reconversion of already converted files"
    )
    
    # Hardware
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Enable GPU acceleration"
    )
    
    parser.add_argument(
        "--gpu-type",
        choices=["nvidia", "amd", "intel", "videotoolbox"],
        help="GPU type for hardware acceleration"
    )
    
    # Concurrency
    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=None,
        help="Number of concurrent conversions"
    )
    
    # Output
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output directory (default: same as input)"
    )
    
    parser.add_argument(
        "--suffix",
        type=str,
        default="",
        help="Suffix for converted files"
    )
    
    # Logging
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v, -vv, -vvv)"
    )
    
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-error output"
    )
    
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Custom log file path"
    )
    
    # Notifications
    parser.add_argument(
        "--webhook",
        type=str,
        help="Webhook URL for notifications"
    )
    
    # Information
    parser.add_argument(
        "--version",
        action="version",
        version="ffmc 1.0.0"
    )
    
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available profiles and exit"
    )
    
    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="Check system dependencies and exit"
    )

    parser.add_argument(
    "--analyze",
    action="store_true",
    help="Analyze and recommend optimal codecs (no conversion)"
)

    parser.add_argument(
        "--max-quality-loss",
        type=float,
        default=5.0,
        help="Maximum acceptable quality loss percentage (default: 5.0)"
    )

    parser.add_argument(
        "--min-compression",
        type=float,
        default=30.0,
        help="Minimum compression percentage (default: 30.0)"
    )
    
    return parser


async def async_main() -> int:
    
    """Main async CLI entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Setup logging first
    log_level = "INFO"
    if args.quiet:
        log_level = "ERROR"
    elif args.verbose == 1:
        log_level = "DEBUG"
    elif args.verbose >= 2:
        log_level = "DEBUG"
    
    logger = setup_logging(
        level=log_level,
        log_file=args.log_file
    )
    
    # Handle special actions
    if args.check_deps:
        # Simple check for ffmpeg/ffprobe
        import shutil
        ffmpeg_found = shutil.which('ffmpeg') is not None
        ffprobe_found = shutil.which('ffprobe') is not None
        
        print(f"ffmpeg: {'✓ Found' if ffmpeg_found else '✗ Not found'}")
        print(f"ffprobe: {'✓ Found' if ffprobe_found else '✗ Not found'}")
        
        return 0 if (ffmpeg_found and ffprobe_found) else 1
    
    if args.list_profiles:
        print("Available profiles:")
        print("  fast      - Quick conversion (CRF 28, veryfast)")
        print("  balanced  - Good quality/speed ratio (CRF 23, medium) [default]")
        print("  quality   - High quality (CRF 18, slow)")
        print("  archive   - Maximum compression (CRF 20, veryslow)")
        return 0
    
    # Load settings
    try:
        settings = Settings.load(
            config_path=args.config,
            profile=args.profile
        )
        
        # Override with CLI arguments
        if args.jobs:
            settings.concurrent_conversions = args.jobs
        if args.gpu:
            settings.hardware_acceleration.enabled = True
        if args.gpu_type:
            settings.hardware_acceleration.type = args.gpu_type
        if args.suffix:
            settings.output_suffix = args.suffix
        if args.output:
            settings.output_directory = args.output
        if args.webhook:
            settings.webhook_url = args.webhook
        
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return 1
    

    if args.analyze:
        from ffmc.analysis.codec_advisor import CodecAdvisor
        from ffmc.analysis.codec_detector import CodecDetector
        
        logger.info("Analyzing videos and recommending codecs...")
        
        advisor = CodecAdvisor()
        detector = CodecDetector(settings)
        
        # Analyze first video (or all if multiple)
        for path in args.paths:
            if path.is_file():
                analysis = await detector.analyze_video(path)
                if analysis:
                    recommendations = advisor.analyze_and_recommend(
                        analysis,
                        max_quality_loss=args.max_quality_loss,
                        min_compression=args.min_compression / 100,
                        gpu_available=settings.hardware_acceleration.type if settings.hardware_acceleration.enabled else None
                    )
                    advisor.print_recommendations(recommendations, analysis)
            elif path.is_dir():
                # Analyze all videos in directory
                from ffmc.io.file_scanner import FileScanner
                scanner = FileScanner(settings)
                videos = await scanner.scan_directory(path)
                
                for video in videos[:5]:  # Limit to first 5 for quick preview
                    analysis = await detector.analyze_video(video)
                    if analysis:
                        recommendations = advisor.analyze_and_recommend(
                            analysis,
                            max_quality_loss=args.max_quality_loss,
                            min_compression=args.min_compression / 100,
                            gpu_available=settings.hardware_acceleration.type if settings.hardware_acceleration.enabled else None
                        )
                        advisor.print_recommendations(recommendations, analysis)
                        input("\nPress Enter for next video...")
        
        return 0
    
    # Validate paths
    if not args.paths and not args.resume:
        logger.error("No paths specified. Use --help for usage information.")
        return 1
    
    # Create orchestrator
    try:
        orchestrator = ConversionOrchestrator(
            settings=settings,
            dry_run=args.dry_run,
            force=args.force,
            resume=args.resume
        )
        
        # Run conversion
        if args.resume:
            success = await orchestrator.resume()
        else:
            success = await orchestrator.run(args.paths)
        
        return 0 if success else 1
        
    except FFMCError as e:
        logger.error(f"Conversion failed: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1
    


def main():
    """Synchronous entry point for console scripts"""
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        return 130
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())