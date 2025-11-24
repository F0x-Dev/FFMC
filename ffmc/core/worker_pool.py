# ffmc/core/worker_pool.py
"""
Worker pool management for concurrent video conversions
Handles task distribution, resource management, and process isolation
"""

import asyncio
import psutil
from pathlib import Path
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from ffmc.config.settings import Settings
from ffmc.conversion.encoder import VideoEncoder
from ffmc.analysis.codec_detector import VideoAnalysis
from ffmc.monitoring.logger import get_logger
from ffmc.utils.exceptions import ConversionError

logger = get_logger('worker_pool')


@dataclass
class WorkerMetrics:
    """Metrics for a single worker"""
    worker_id: int
    current_task: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_processing_time: float = 0.0
    cpu_affinity: list = field(default_factory=list)
    is_busy: bool = False
    last_task_time: Optional[datetime] = None


class Worker:
    """Individual worker for processing video conversions"""
    
    def __init__(
        self,
        worker_id: int,
        encoder: VideoEncoder,
        settings: Settings
    ):
        self.worker_id = worker_id
        self.encoder = encoder
        self.settings = settings
        self.metrics = WorkerMetrics(worker_id=worker_id)
        self.semaphore = asyncio.Semaphore(1)
        
        # Set CPU affinity if enabled
        if settings.cpu_affinity:
            self._set_cpu_affinity()
    
    def _set_cpu_affinity(self):
        """Set CPU affinity for optimal performance"""
        try:
            cpu_count = psutil.cpu_count(logical=False) or 1
            
            # Distribute workers across physical cores
            cores_per_worker = max(1, cpu_count // self.settings.concurrent_conversions)
            start_core = (self.worker_id * cores_per_worker) % cpu_count
            end_core = min(start_core + cores_per_worker, cpu_count)
            
            self.metrics.cpu_affinity = list(range(start_core, end_core))
            
            logger.debug(
                f"Worker {self.worker_id} assigned to cores "
                f"{self.metrics.cpu_affinity}"
            )
        except Exception as e:
            logger.warning(f"Failed to set CPU affinity: {e}")
    
    async def process(
        self,
        video_path: Path,
        analysis: VideoAnalysis,
        progress_callback: Optional[Callable] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single video conversion
        
        Args:
            video_path: Path to video file
            analysis: Video analysis result
            progress_callback: Optional callback for progress updates
            
        Returns:
            Conversion result dict or None if failed
        """
        async with self.semaphore:
            self.metrics.is_busy = True
            self.metrics.current_task = video_path.name
            start_time = datetime.now()
            
            try:
                logger.info(
                    f"Worker {self.worker_id} starting: {video_path.name}"
                )
                
                # Execute conversion
                result = await self.encoder.convert_video(
                    video_path=video_path,
                    analysis=analysis,
                    progress_callback=progress_callback,
                    cpu_affinity=self.metrics.cpu_affinity
                )
                
                # Update metrics on success
                processing_time = (datetime.now() - start_time).total_seconds()
                self.metrics.tasks_completed += 1
                self.metrics.total_processing_time += processing_time
                self.metrics.last_task_time = datetime.now()
                
                logger.info(
                    f"Worker {self.worker_id} completed: {video_path.name} "
                    f"in {processing_time:.1f}s"
                )
                
                return result
                
            except ConversionError as e:
                logger.error(
                    f"Worker {self.worker_id} conversion failed: "
                    f"{video_path.name}: {e}"
                )
                self.metrics.tasks_failed += 1
                return None
                
            except Exception as e:
                logger.exception(
                    f"Worker {self.worker_id} unexpected error: "
                    f"{video_path.name}: {e}"
                )
                self.metrics.tasks_failed += 1
                return None
                
            finally:
                self.metrics.is_busy = False
                self.metrics.current_task = None


class WorkerPool:
    """
    Manages a pool of workers for concurrent video conversions
    
    Features:
    - Automatic work distribution
    - CPU affinity management
    - Resource monitoring
    - Graceful shutdown
    """
    
    def __init__(self, max_workers: int, settings: Settings):
        self.max_workers = max_workers
        self.settings = settings
        self.workers: list[Worker] = []
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: set = set()
        self.shutdown_event = asyncio.Event()
        
        # Create encoder instance (shared configuration)
        self.encoder = VideoEncoder(settings)
        
        # Initialize workers
        self._initialize_workers()
        
        logger.info(f"Worker pool initialized with {max_workers} workers")
    
    def _initialize_workers(self):
        """Initialize worker instances"""
        for i in range(self.max_workers):
            worker = Worker(
                worker_id=i,
                encoder=self.encoder,
                settings=self.settings
            )
            self.workers.append(worker)
    
    async def submit(
        self,
        video_path: Path,
        analysis: VideoAnalysis,
        progress_callback: Optional[Callable] = None
    ) -> asyncio.Task:
        """
        Submit a conversion task to the pool
        
        Args:
            video_path: Path to video file
            analysis: Video analysis result
            progress_callback: Optional progress callback
            
        Returns:
            Asyncio task for the conversion
        """
        task = asyncio.create_task(
            self._process_task(video_path, analysis, progress_callback)
        )
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)
        return task
    
    async def _process_task(
        self,
        video_path: Path,
        analysis: VideoAnalysis,
        progress_callback: Optional[Callable]
    ) -> Optional[Dict[str, Any]]:
        """Process a task using available worker"""
        # Wait for available worker
        available_worker = await self._get_available_worker()
        
        if self.shutdown_event.is_set():
            logger.warning(f"Skipping {video_path.name}: shutdown in progress")
            return None
        
        # Process with worker
        return await available_worker.process(
            video_path, analysis, progress_callback
        )
    
    async def _get_available_worker(self) -> Worker:
        """Get next available worker (blocks until one is free)"""
        while not self.shutdown_event.is_set():
            # Check for available worker
            for worker in self.workers:
                if not worker.metrics.is_busy:
                    return worker
            
            # No workers available, wait briefly
            await asyncio.sleep(0.1)
        
        # If shutdown, return first worker (won't be used)
        return self.workers[0]
    
    async def wait_all(self):
        """Wait for all active tasks to complete"""
        if self.active_tasks:
            logger.info(f"Waiting for {len(self.active_tasks)} active tasks...")
            await asyncio.gather(*self.active_tasks, return_exceptions=True)
    
    async def shutdown(self, wait: bool = True):
        """
        Shutdown the worker pool
        
        Args:
            wait: If True, wait for active tasks to complete
        """
        logger.info("Initiating worker pool shutdown...")
        self.shutdown_event.set()
        
        if wait:
            await self.wait_all()
        
        logger.info("Worker pool shutdown complete")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get aggregated worker metrics"""
        total_completed = sum(w.metrics.tasks_completed for w in self.workers)
        total_failed = sum(w.metrics.tasks_failed for w in self.workers)
        total_time = sum(w.metrics.total_processing_time for w in self.workers)
        busy_workers = sum(1 for w in self.workers if w.metrics.is_busy)
        
        avg_time = (
            total_time / total_completed if total_completed > 0 else 0
        )
        
        return {
            'total_workers': self.max_workers,
            'busy_workers': busy_workers,
            'idle_workers': self.max_workers - busy_workers,
            'tasks_completed': total_completed,
            'tasks_failed': total_failed,
            'total_processing_time': total_time,
            'avg_processing_time': avg_time,
            'active_tasks': len(self.active_tasks),
            'worker_details': [
                {
                    'id': w.worker_id,
                    'busy': w.metrics.is_busy,
                    'current_task': w.metrics.current_task,
                    'completed': w.metrics.tasks_completed,
                    'failed': w.metrics.tasks_failed,
                    'cpu_cores': w.metrics.cpu_affinity
                }
                for w in self.workers
            ]
        }
    
    def print_status(self):
        """Print current worker pool status"""
        metrics = self.get_metrics()
        
        logger.info("=" * 60)
        logger.info("WORKER POOL STATUS")
        logger.info("=" * 60)
        logger.info(
            f"Workers: {metrics['busy_workers']}/{metrics['total_workers']} busy"
        )
        logger.info(f"Tasks completed: {metrics['tasks_completed']}")
        logger.info(f"Tasks failed: {metrics['tasks_failed']}")
        logger.info(
            f"Avg processing time: {metrics['avg_processing_time']:.1f}s"
        )
        logger.info("=" * 60)