"""
Main conversion orchestrator
Coordinates all conversion operations
"""

import asyncio
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from ffmc.config.settings import Settings
from ffmc.io.file_scanner import FileScanner
from ffmc.analysis.codec_detector import CodecDetector
from ffmc.conversion.encoder import VideoEncoder
from ffmc.persistence.database import ConversionDatabase
from ffmc.persistence.state_manager import StateManager
from ffmc.monitoring.logger import get_logger
from ffmc.monitoring.progress_tracker import ProgressTracker
from ffmc.monitoring.metrics_collector import MetricsCollector
from ffmc.monitoring.notifier import Notifier
from ffmc.core.worker_pool import WorkerPool
from ffmc.utils.exceptions import FFMCError

logger = get_logger('orchestrator')
perf_logger = get_logger('performance')


class ConversionOrchestrator:
    """
    Main orchestrator for video conversion operations
    
    Responsibilities:
    - Coordinate scanning, analysis, and conversion
    - Manage worker pool and concurrency
    - Track progress and metrics
    - Handle errors and recovery
    """
    
    def __init__(
        self,
        settings: Settings,
        dry_run: bool = False,
        force: bool = False,
        resume: bool = False
    ):
        self.settings = settings
        self.dry_run = dry_run
        self.force = force
        self.resume_mode = resume
        
        # Initialize components
        self.scanner = FileScanner(settings)
        self.detector = CodecDetector(settings)
        self.encoder = VideoEncoder(settings)
        self.database = ConversionDatabase(settings.database_path)
        self.state_manager = StateManager(settings.state_file)
        self.progress = ProgressTracker()
        self.metrics = MetricsCollector()
        self.notifier = Notifier(settings.webhook_url) if settings.webhook_url else None
        
        # Worker pool for concurrent conversions
        self.worker_pool = WorkerPool(
            max_workers=settings.concurrent_conversions,
            settings=settings
        )
        
        self.start_time: Optional[datetime] = None
        
    async def run(self, paths: List[Path]) -> bool:
        """
        Main entry point for conversion process
        
        Args:
            paths: List of directories or files to process
            
        Returns:
            True if successful, False otherwise
        """
        self.start_time = datetime.now()
        logger.info("=" * 80)
        logger.info("FFMC Conversion Started")
        logger.info("=" * 80)
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE CONVERSION'}")
        logger.info(f"Profile: {self.settings.video_quality.preset}")
        logger.info(f"Concurrent workers: {self.settings.concurrent_conversions}")
        logger.info(f"Hardware acceleration: {self.settings.hardware_acceleration.enabled}")
        
        try:
            # Step 1: Scan for video files
            logger.info("Step 1/4: Scanning for video files...")
            video_files = await self._scan_paths(paths)
            
            if not video_files:
                logger.warning("No video files found")
                return False
            
            logger.info(f"Found {len(video_files)} video files")
            
            # Step 2: Analyze videos
            logger.info("Step 2/4: Analyzing video files...")
            analysis_results = await self._analyze_videos(video_files)
            
            # Step 3: Filter videos that need conversion
            logger.info("Step 3/4: Determining conversion requirements...")
            conversions_needed = self._filter_conversions(video_files, analysis_results)
            
            if not conversions_needed:
                logger.info("All videos are already in optimal format")
                return True
            
            logger.info(f"{len(conversions_needed)} videos need conversion")
            
            # Step 4: Execute conversions
            logger.info("Step 4/4: Converting videos...")
            
            if self.dry_run:
                await self._dry_run_preview(conversions_needed)
                return True
            else:
                success = await self._execute_conversions(conversions_needed)
                
                # Send completion notification
                if self.notifier:
                    await self._send_completion_notification(success)
                
                return success
                
        except KeyboardInterrupt:
            logger.warning("Conversion interrupted by user")
            await self._cleanup()
            return False
            
        except Exception as e:
            logger.exception(f"Fatal error during conversion: {e}")
            await self._cleanup()
            return False
            
        finally:
            await self._finalize()
    
    async def resume(self) -> bool:
        """Resume a previous conversion job"""
        logger.info("Resuming previous conversion job...")
        
        state = self.state_manager.load()
        if not state or not state.get('pending'):
            logger.warning("No conversion state found to resume")
            return False
        
        pending_files = [Path(p) for p in state['pending']]
        logger.info(f"Resuming {len(pending_files)} pending conversions")
        
        # Load analysis from database
        conversions_needed = []
        for file_path in pending_files:
            analysis = self.database.get_analysis(file_path)
            if analysis:
                conversions_needed.append((file_path, analysis))
        
        if not conversions_needed:
            logger.warning("No valid conversions to resume")
            return False
        
        return await self._execute_conversions(conversions_needed)
    
    async def _scan_paths(self, paths: List[Path]) -> List[Path]:
        """Scan paths for video files"""
        all_files = []
        
        with self.progress.task("Scanning directories") as task:
            for path in paths:
                if path.is_file():
                    if self.scanner.is_video_file(path):
                        all_files.append(path)
                elif path.is_dir():
                    files = await self.scanner.scan_directory(path)
                    all_files.extend(files)
                    task.update(advance=len(files))
                else:
                    logger.warning(f"Invalid path: {path}")
        
        return all_files
    
    async def _analyze_videos(self, video_files: List[Path]) -> dict:
        """Analyze all video files concurrently"""
        results = {}
        
        with self.progress.task("Analyzing videos", total=len(video_files)) as task:
            # Analyze in batches to avoid overwhelming the system
            batch_size = 50
            for i in range(0, len(video_files), batch_size):
                batch = video_files[i:i + batch_size]
                
                tasks = [
                    self.detector.analyze_video(video)
                    for video in batch
                ]
                
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for video, result in zip(batch, batch_results):
                    if isinstance(result, Exception):
                        logger.error(f"Analysis failed for {video.name}: {result}")
                        results[video] = None
                    else:
                        results[video] = result
                        # Cache analysis in database
                        self.database.store_analysis(video, result)
                    
                    task.update(advance=1)
        
        return results
    
    def _filter_conversions(
        self,
        video_files: List[Path],
        analysis_results: dict
    ) -> List[tuple]:
        """Filter videos that need conversion"""
        conversions_needed = []
        
        for video in video_files:
            analysis = analysis_results.get(video)
            
            if analysis is None:
                logger.warning(f"Skipping {video.name}: analysis failed")
                continue
            
            # Check if already converted (unless force mode)
            if not self.force and self.database.is_converted(video):
                logger.debug(f"Skipping {video.name}: already converted")
                continue
            
            # Check if conversion is needed
            if analysis.needs_conversion:
                conversions_needed.append((video, analysis))
            else:
                logger.debug(f"Skipping {video.name}: already optimal format")
        
        # Sort by file size (largest first for better parallelization)
        conversions_needed.sort(
            key=lambda x: x[1].file_size,
            reverse=True
        )
        
        return conversions_needed
    
    async def _dry_run_preview(self, conversions: List[tuple]):
        """Show preview of conversions without executing"""
        logger.info("=" * 80)
        logger.info("DRY RUN - Preview of planned conversions")
        logger.info("=" * 80)
        
        total_size = 0
        estimated_output = 0
        
        for video_path, analysis in conversions:
            # Estimate output size (typically 40-60% reduction for H.265)
            compression_ratio = 0.6  # Conservative estimate
            estimated_size = int(analysis.file_size * compression_ratio)
            savings = analysis.file_size - estimated_size
            
            total_size += analysis.file_size
            estimated_output += estimated_size
            
            logger.info(f"\n{video_path.name}")
            logger.info(f"  Current: {self._format_size(analysis.file_size)}")
            logger.info(f"  Codec: {analysis.video_codec} -> {self.settings.target_video_codec}")
            logger.info(f"  Resolution: {analysis.resolution}")
            logger.info(f"  Estimated output: {self._format_size(estimated_size)}")
            logger.info(f"  Estimated savings: {self._format_size(savings)} ({savings/analysis.file_size*100:.1f}%)")
        
        total_savings = total_size - estimated_output
        
        logger.info("\n" + "=" * 80)
        logger.info("Summary")
        logger.info("=" * 80)
        logger.info(f"Total files: {len(conversions)}")
        logger.info(f"Total size: {self._format_size(total_size)}")
        logger.info(f"Estimated output: {self._format_size(estimated_output)}")
        logger.info(f"Estimated savings: {self._format_size(total_savings)} ({total_savings/total_size*100:.1f}%)")
        logger.info("=" * 80)
    
    async def _execute_conversions(self, conversions: List[tuple]) -> bool:
        """Execute actual conversions"""
        # Save state for resume capability
        self.state_manager.save({
            'pending': [str(v[0]) for v in conversions],
            'timestamp': datetime.now().isoformat()
        })
        
        # Start metrics collection
        self.metrics.start()
        
        # Submit all conversion jobs to worker pool
        with self.progress.conversion_progress(total=len(conversions)) as progress:
            tasks = []
            for video_path, analysis in conversions:
                task = self.worker_pool.submit(
                    video_path,
                    analysis,
                    progress_callback=progress.update_file
                )
                tasks.append(task)
            
            # Wait for all conversions to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        successful = 0
        failed = 0
        skipped = 0
        
        for (video_path, analysis), result in zip(conversions, results):
            if isinstance(result, Exception):
                logger.error(f"Conversion failed: {video_path.name}: {result}")
                self.database.mark_failed(video_path, str(result))
                failed += 1
            elif result is None:
                logger.warning(f"Conversion skipped: {video_path.name}")
                skipped += 1
            else:
                logger.info(f"Conversion successful: {video_path.name}")
                self.database.mark_completed(
                    video_path,
                    analysis.file_size,
                    result['output_size'],
                    result['duration']
                )
                successful += 1
                
                # Update state
                self.state_manager.mark_completed(video_path)
        
        # Print summary
        self._print_summary(successful, failed, skipped)
        
        return failed == 0
    
    async def _send_completion_notification(self, success: bool):
        """Send completion notification via webhook"""
        if not self.notifier:
            return
        
        stats = self.database.get_statistics()
        
        message = f"""
🎬 **FFMC Conversion Complete**

{'✅ Success' if success else '⚠️ Completed with errors'}

📊 **Statistics:**
✓ Completed: {stats['completed']}
✗ Failed: {stats['failed']}
⊘ Skipped: {stats['skipped']}

💾 **Space Saved:** {self._format_size(stats['total_savings'])}
⏱️ **Duration:** {self._format_duration(datetime.now() - self.start_time)}
        """
        
        try:
            await self.notifier.send(message)
        except Exception as e:
            logger.warning(f"Failed to send notification: {e}")
    
    def _print_summary(self, successful: int, failed: int, skipped: int):
        """Print conversion summary"""
        elapsed = datetime.now() - self.start_time
        stats = self.database.get_statistics()
        
        logger.info("\n" + "=" * 80)
        logger.info("CONVERSION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Successful: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Skipped: {skipped}")
        logger.info(f"\nTotal space saved: {self._format_size(stats['total_savings'])}")
        logger.info(f"Average savings: {stats['avg_savings_percent']:.1f}%")
        logger.info(f"\nElapsed time: {self._format_duration(elapsed)}")
        logger.info(f"Average time per video: {self._format_duration(elapsed / max(successful, 1))}")
        logger.info("=" * 80)
        
        # Log to performance logger
        perf_logger.info("Conversion batch completed", extra={
            'successful': successful,
            'failed': failed,
            'skipped': skipped,
            'duration': elapsed.total_seconds(),
            'space_saved': stats['total_savings']
        })
    
    async def _cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up resources...")
        await self.worker_pool.shutdown()
    
    async def _finalize(self):
        """Finalize conversion process"""
        if self.metrics:
            self.metrics.stop()
            self.metrics.save_report()
        
        await self.worker_pool.shutdown()
        self.database.close()
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    
    @staticmethod
    def _format_duration(duration) -> str:
        """Format timedelta to human-readable duration"""
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"