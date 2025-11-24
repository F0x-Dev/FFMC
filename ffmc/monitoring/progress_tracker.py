# ffmc/monitoring/progress_tracker.py
"""
Progress tracking with rich console output
Provides real-time feedback on conversion progress
"""

from typing import Optional, Dict, Any
from contextlib import contextmanager
from datetime import datetime
import sys

try:
    from rich.console import Console
    from rich.progress import (
        Progress, 
        TaskID, 
        TextColumn, 
        BarColumn, 
        TimeRemainingColumn,
        TimeElapsedColumn,
        SpinnerColumn
    )
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from ffmc.monitoring.logger import get_logger

logger = get_logger('progress_tracker')


class ProgressTracker:
    """
    Manages progress tracking and display for conversions
    
    Uses rich library if available, falls back to simple logging
    """
    
    def __init__(self):
        self.console = Console() if RICH_AVAILABLE else None
        self.progress = None
        self.current_tasks: Dict[str, Any] = {}
        self.start_time = None
    
    @contextmanager
    def task(self, description: str, total: Optional[int] = None):
        """
        Create a simple progress task
        
        Args:
            description: Task description
            total: Total items (if known)
        """
        if RICH_AVAILABLE and self.console:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn() if total else TextColumn(""),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%") if total else TextColumn(""),
                TimeElapsedColumn(),
                console=self.console
            ) as progress:
                task_id = progress.add_task(description, total=total or 100)
                
                class TaskUpdater:
                    def update(self, advance: int = 1):
                        progress.update(task_id, advance=advance)
                
                yield TaskUpdater()
        else:
            logger.info(f"Starting: {description}")
            
            class SimpleUpdater:
                def __init__(self, desc):
                    self.desc = desc
                    self.count = 0
                
                def update(self, advance: int = 1):
                    self.count += advance
                    if total and self.count % max(1, total // 10) == 0:
                        logger.info(f"{self.desc}: {self.count}/{total}")
            
            yield SimpleUpdater(description)
    
    @contextmanager
    def conversion_progress(self, total: int):
        """
        Create a comprehensive conversion progress tracker
        
        Args:
            total: Total number of videos to convert
        """
        self.start_time = datetime.now()
        
        if RICH_AVAILABLE and self.console:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold green]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.completed}/{task.total}"),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=self.console,
                expand=True
            ) as progress:
                
                # Main task
                main_task = progress.add_task(
                    "Overall Progress",
                    total=total
                )
                
                # Individual file task
                file_task = progress.add_task(
                    "Current File",
                    total=100,
                    visible=False
                )
                
                class ConversionUpdater:
                    def __init__(self, prog, main_id, file_id):
                        self.progress = prog
                        self.main_task_id = main_id
                        self.file_task_id = file_id
                        self.current_file = None
                    
                    def update_file(
                        self,
                        filename: str,
                        progress_pct: float = 0,
                        completed: bool = False
                    ):
                        if completed:
                            self.progress.update(
                                self.main_task_id,
                                advance=1
                            )
                            self.progress.update(
                                self.file_task_id,
                                visible=False
                            )
                        else:
                            if filename != self.current_file:
                                self.current_file = filename
                                self.progress.update(
                                    self.file_task_id,
                                    description=f"Converting: {filename}",
                                    completed=0,
                                    visible=True
                                )
                            
                            self.progress.update(
                                self.file_task_id,
                                completed=int(progress_pct)
                            )
                
                yield ConversionUpdater(progress, main_task, file_task)
        else:
            # Simple fallback
            class SimpleConversionUpdater:
                def __init__(self, tot):
                    self.total = tot
                    self.completed = 0
                
                def update_file(
                    self,
                    filename: str,
                    progress_pct: float = 0,
                    completed: bool = False
                ):
                    if completed:
                        self.completed += 1
                        logger.info(
                            f"Progress: {self.completed}/{self.total} - "
                            f"Completed: {filename}"
                        )
                    elif progress_pct == 0:
                        logger.info(f"Starting: {filename}")
            
            yield SimpleConversionUpdater(total)
    
    def print_summary_table(self, data: Dict[str, Any]):
        """
        Print a formatted summary table
        
        Args:
            data: Dictionary with summary data
        """
        if RICH_AVAILABLE and self.console:
            table = Table(title="Conversion Summary", show_header=True)
            
            table.add_column("Metric", style="cyan", no_wrap=True)
            table.add_column("Value", style="green")
            
            for key, value in data.items():
                table.add_row(str(key), str(value))
            
            self.console.print(table)
        else:
            logger.info("=" * 60)
            logger.info("CONVERSION SUMMARY")
            logger.info("=" * 60)
            for key, value in data.items():
                logger.info(f"{key}: {value}")
            logger.info("=" * 60)
    
    def print_worker_status(self, workers_data: list):
        """
        Print worker status table
        
        Args:
            workers_data: List of worker status dictionaries
        """
        if RICH_AVAILABLE and self.console:
            table = Table(title="Worker Status", show_header=True)
            
            table.add_column("Worker ID", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Current Task", style="yellow")
            table.add_column("Completed", style="blue")
            table.add_column("Failed", style="red")
            
            for worker in workers_data:
                status = "BUSY" if worker['busy'] else "IDLE"
                task = worker['current_task'] or "-"
                
                table.add_row(
                    str(worker['id']),
                    status,
                    task,
                    str(worker['completed']),
                    str(worker['failed'])
                )
            
            self.console.print(table)
        else:
            logger.info("=" * 60)
            logger.info("WORKER STATUS")
            logger.info("=" * 60)
            for worker in workers_data:
                logger.info(
                    f"Worker {worker['id']}: "
                    f"{'BUSY' if worker['busy'] else 'IDLE'} - "
                    f"Task: {worker['current_task'] or 'None'}"
                )
            logger.info("=" * 60)
    
    def print_error(self, message: str):
        """Print error message"""
        if RICH_AVAILABLE and self.console:
            self.console.print(f"[bold red]ERROR:[/bold red] {message}")
        else:
            logger.error(message)
    
    def print_warning(self, message: str):
        """Print warning message"""
        if RICH_AVAILABLE and self.console:
            self.console.print(f"[bold yellow]WARNING:[/bold yellow] {message}")
        else:
            logger.warning(message)
    
    def print_success(self, message: str):
        """Print success message"""
        if RICH_AVAILABLE and self.console:
            self.console.print(f"[bold green]SUCCESS:[/bold green] {message}")
        else:
            logger.info(message)
    
    def print_info(self, message: str):
        """Print info message"""
        if RICH_AVAILABLE and self.console:
            self.console.print(f"[bold blue]INFO:[/bold blue] {message}")
        else:
            logger.info(message)