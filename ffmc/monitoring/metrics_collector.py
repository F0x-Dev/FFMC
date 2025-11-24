# ffmc/monitoring/metrics_collector.py
"""
Performance metrics collection and reporting
Tracks system resources, conversion speeds, and efficiency
"""

import psutil
import time
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, asdict

from ffmc.monitoring.logger import get_logger

logger = get_logger('metrics')


@dataclass
class SystemMetrics:
    """System resource metrics at a point in time"""
    timestamp: str
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    disk_io_read_mb: float
    disk_io_write_mb: float


@dataclass
class ConversionMetrics:
    """Metrics for a single conversion"""
    file_name: str
    original_size_mb: float
    converted_size_mb: float
    duration_seconds: float
    speed_mbps: float
    compression_ratio: float
    cpu_avg: float
    memory_avg: float


class MetricsCollector:
    """
    Collects and aggregates performance metrics
    
    Tracks:
    - System resource usage (CPU, memory, disk I/O)
    - Conversion performance
    - Efficiency metrics
    """
    
    def __init__(self, sample_interval: float = 5.0):
        self.sample_interval = sample_interval
        self.is_collecting = False
        self.system_metrics: List[SystemMetrics] = []
        self.conversion_metrics: List[ConversionMetrics] = []
        self.start_time: datetime = None
        self.last_disk_io = psutil.disk_io_counters()
    
    def start(self):
        """Start metrics collection"""
        self.start_time = datetime.now()
        self.is_collecting = True
        self.system_metrics = []
        self.conversion_metrics = []
        logger.info("Metrics collection started")
    
    def stop(self):
        """Stop metrics collection"""
        self.is_collecting = False
        logger.info("Metrics collection stopped")
    
    def collect_system_snapshot(self):
        """Collect current system metrics"""
        if not self.is_collecting:
            return
        
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            if self.last_disk_io:
                read_mb = (disk_io.read_bytes - self.last_disk_io.read_bytes) / (1024 * 1024)
                write_mb = (disk_io.write_bytes - self.last_disk_io.write_bytes) / (1024 * 1024)
            else:
                read_mb = 0
                write_mb = 0
            
            self.last_disk_io = disk_io
            
            snapshot = SystemMetrics(
                timestamp=datetime.now().isoformat(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_gb=memory.used / (1024 ** 3),
                disk_io_read_mb=read_mb,
                disk_io_write_mb=write_mb
            )
            
            self.system_metrics.append(snapshot)
            
        except Exception as e:
            logger.warning(f"Failed to collect system metrics: {e}")
    
    def record_conversion(
        self,
        file_name: str,
        original_size: int,
        converted_size: int,
        duration: float
    ):
        """
        Record metrics for a completed conversion
        
        Args:
            file_name: Name of converted file
            original_size: Original file size in bytes
            converted_size: Converted file size in bytes
            duration: Conversion duration in seconds
        """
        original_mb = original_size / (1024 * 1024)
        converted_mb = converted_size / (1024 * 1024)
        
        # Calculate conversion speed
        speed_mbps = original_mb / duration if duration > 0 else 0
        
        # Compression ratio
        compression_ratio = converted_size / original_size if original_size > 0 else 1.0
        
        # Get average system usage during conversion (last few samples)
        recent_samples = self.system_metrics[-10:] if self.system_metrics else []
        cpu_avg = (
            sum(s.cpu_percent for s in recent_samples) / len(recent_samples)
            if recent_samples else 0
        )
        memory_avg = (
            sum(s.memory_percent for s in recent_samples) / len(recent_samples)
            if recent_samples else 0
        )
        
        metrics = ConversionMetrics(
            file_name=file_name,
            original_size_mb=original_mb,
            converted_size_mb=converted_mb,
            duration_seconds=duration,
            speed_mbps=speed_mbps,
            compression_ratio=compression_ratio,
            cpu_avg=cpu_avg,
            memory_avg=memory_avg
        )
        
        self.conversion_metrics.append(metrics)
        logger.debug(f"Recorded metrics for {file_name}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get aggregated metrics summary"""
        if not self.conversion_metrics:
            return {
                'total_conversions': 0,
                'total_duration': 0,
                'message': 'No conversions recorded'
            }
        
        total_original = sum(m.original_size_mb for m in self.conversion_metrics)
        total_converted = sum(m.converted_size_mb for m in self.conversion_metrics)
        total_duration = sum(m.duration_seconds for m in self.conversion_metrics)
        
        avg_speed = (
            sum(m.speed_mbps for m in self.conversion_metrics) / 
            len(self.conversion_metrics)
        )
        
        avg_compression = (
            sum(m.compression_ratio for m in self.conversion_metrics) / 
            len(self.conversion_metrics)
        )
        
        # System metrics summary
        if self.system_metrics:
            avg_cpu = sum(s.cpu_percent for s in self.system_metrics) / len(self.system_metrics)
            max_cpu = max(s.cpu_percent for s in self.system_metrics)
            avg_memory = sum(s.memory_percent for s in self.system_metrics) / len(self.system_metrics)
            max_memory = max(s.memory_percent for s in self.system_metrics)
            total_disk_read = sum(s.disk_io_read_mb for s in self.system_metrics)
            total_disk_write = sum(s.disk_io_write_mb for s in self.system_metrics)
        else:
            avg_cpu = max_cpu = avg_memory = max_memory = 0
            total_disk_read = total_disk_write = 0
        
        return {
            'total_conversions': len(self.conversion_metrics),
            'total_duration_seconds': total_duration,
            'total_duration_formatted': self._format_duration(total_duration),
            'total_original_size_mb': total_original,
            'total_converted_size_mb': total_converted,
            'total_space_saved_mb': total_original - total_converted,
            'avg_conversion_speed_mbps': avg_speed,
            'avg_compression_ratio': avg_compression,
            'avg_cpu_percent': avg_cpu,
            'max_cpu_percent': max_cpu,
            'avg_memory_percent': avg_memory,
            'max_memory_percent': max_memory,
            'total_disk_read_mb': total_disk_read,
            'total_disk_write_mb': total_disk_write,
            'system_samples': len(self.system_metrics)
        }
    
    def save_report(self, output_dir: Path = Path('logs')):
        """Save detailed metrics report to JSON"""
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = output_dir / f'metrics_report_{timestamp}.json'
        
        report = {
            'summary': self.get_summary(),
            'conversions': [asdict(m) for m in self.conversion_metrics],
            'system_metrics': [asdict(m) for m in self.system_metrics],
            'collection_period': {
                'start': self.start_time.isoformat() if self.start_time else None,
                'end': datetime.now().isoformat()
            }
        }
        
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2)
            
            logger.info(f"Metrics report saved: {report_path}")
            
        except Exception as e:
            logger.error(f"Failed to save metrics report: {e}")
    
    def print_summary(self):
        """Print metrics summary to log"""
        summary = self.get_summary()
        
        logger.info("=" * 80)
        logger.info("PERFORMANCE METRICS SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total conversions: {summary['total_conversions']}")
        logger.info(f"Total duration: {summary['total_duration_formatted']}")
        logger.info(
            f"Space saved: {summary['total_space_saved_mb']:.2f} MB "
            f"({(1 - summary['avg_compression_ratio']) * 100:.1f}%)"
        )
        logger.info(f"Avg conversion speed: {summary['avg_conversion_speed_mbps']:.2f} MB/s")
        logger.info(f"Avg CPU usage: {summary['avg_cpu_percent']:.1f}% "
                   f"(peak: {summary['max_cpu_percent']:.1f}%)")
        logger.info(f"Avg memory usage: {summary['avg_memory_percent']:.1f}% "
                   f"(peak: {summary['max_memory_percent']:.1f}%)")
        logger.info(f"Disk I/O - Read: {summary['total_disk_read_mb']:.2f} MB, "
                   f"Write: {summary['total_disk_write_mb']:.2f} MB")
        logger.info("=" * 80)
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format seconds to human-readable duration"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"