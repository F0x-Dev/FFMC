"""
Advanced logging configuration for FFMC
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    """Colored console output formatter"""
    
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'
    }
    
    def format(self, record):
        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            levelname = record.levelname
            if levelname in self.COLORS:
                record.levelname = (
                    f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
                )
        return super().format(record)


class StructuredFormatter(logging.Formatter):
    """JSON-like structured logging formatter"""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        if hasattr(record, 'file_path'):
            log_data['file'] = str(record.file_path)
        
        if hasattr(record, 'duration'):
            log_data['duration'] = record.duration
        
        return str(log_data)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    log_dir: Path = Path("logs"),
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Setup comprehensive logging system
    
    Creates three log files:
    - ffmc.log: All logs
    - errors.log: Errors only
    - performance.log: Performance metrics
    """
    
    # Create log directory
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler (colored, INFO+)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(ColoredFormatter(
        fmt='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    ))
    root_logger.addHandler(console_handler)
    
    # Main log file (all logs, rotating)
    if log_file is None:
        log_file = log_dir / "ffmc.log"
    
    main_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    main_handler.setLevel(logging.DEBUG)
    main_handler.setFormatter(logging.Formatter(
        fmt='%(asctime)s [%(levelname)8s] %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    root_logger.addHandler(main_handler)
    
    # Error log file (errors only, daily rotation)
    error_handler = TimedRotatingFileHandler(
        log_dir / "errors.log",
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(
        fmt='%(asctime)s [%(levelname)s] %(name)s.%(funcName)s:%(lineno)d\n'
            '%(message)s\n'
            '%(pathname)s\n',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    root_logger.addHandler(error_handler)
    
    # Performance log (structured, for metrics)
    perf_handler = RotatingFileHandler(
        log_dir / "performance.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    perf_handler.setLevel(logging.INFO)
    perf_handler.setFormatter(StructuredFormatter())
    
    # Only attach to performance logger
    perf_logger = logging.getLogger('ffmc.performance')
    perf_logger.addHandler(perf_handler)
    perf_logger.propagate = False  # Don't send to root logger
    
    # Suppress noisy third-party loggers
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    logger = logging.getLogger('ffmc')
    logger.info(f"Logging initialized at {level} level")
    logger.debug(f"Log files: {log_dir.absolute()}")
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance"""
    return logging.getLogger(f'ffmc.{name}')