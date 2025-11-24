# ffmc/io/file_scanner.py
"""
File system scanner with optimized directory traversal
Supports recursive scanning, filtering, and network path detection
"""

import asyncio
from pathlib import Path
from typing import List, Set, Optional
from concurrent.futures import ThreadPoolExecutor
import os

from ffmc.config.settings import Settings
from ffmc.monitoring.logger import get_logger
from ffmc.utils.exceptions import FileSystemError

logger = get_logger('file_scanner')


class FileScanner:
    """
    High-performance file system scanner for video files
    
    Features:
    - Recursive directory traversal
    - Extension filtering
    - Network path detection and optimization
    - Parallel scanning for large directories
    - Permission error handling
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.extensions = set(
            ext.lower().lstrip('.') 
            for ext in settings.extensions
        )
        self.max_scan_workers = min(4, os.cpu_count() or 2)
        self.executor = ThreadPoolExecutor(max_workers=self.max_scan_workers)
    
    async def scan_directory(
        self, 
        directory: Path,
        recursive: bool = True
    ) -> List[Path]:
        """
        Scan directory for video files
        
        Args:
            directory: Root directory to scan
            recursive: If True, scan subdirectories
            
        Returns:
            List of video file paths
            
        Raises:
            FileSystemError: If directory is invalid or inaccessible
        """
        if not directory.exists():
            raise FileSystemError(f"Directory does not exist: {directory}")
        
        if not directory.is_dir():
            raise FileSystemError(f"Path is not a directory: {directory}")
        
        logger.info(f"Scanning directory: {directory}")
        
        # Detect if network path and optimize
        is_network = self._is_network_path(directory)
        if is_network:
            logger.info(f"Network path detected: {directory}")
        
        # Perform scan
        try:
            if recursive:
                video_files = await self._scan_recursive(directory)
            else:
                video_files = await self._scan_flat(directory)
            
            logger.info(
                f"Found {len(video_files)} video files in {directory}"
            )
            return video_files
            
        except PermissionError as e:
            raise FileSystemError(
                f"Permission denied accessing {directory}: {e}"
            )
        except Exception as e:
            raise FileSystemError(
                f"Error scanning {directory}: {e}"
            )
    
    async def scan_multiple(
        self,
        directories: List[Path]
    ) -> List[Path]:
        """
        Scan multiple directories concurrently
        
        Args:
            directories: List of directories to scan
            
        Returns:
            Combined list of video files from all directories
        """
        tasks = [
            self.scan_directory(directory)
            for directory in directories
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_files = []
        for directory, result in zip(directories, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to scan {directory}: {result}")
            else:
                all_files.extend(result)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_files = []
        for file_path in all_files:
            if file_path not in seen:
                seen.add(file_path)
                unique_files.append(file_path)
        
        return unique_files
    
    async def _scan_recursive(self, directory: Path) -> List[Path]:
        """Recursively scan directory and subdirectories"""
        loop = asyncio.get_event_loop()
        
        # Use thread pool for I/O-bound directory traversal
        video_files = await loop.run_in_executor(
            self.executor,
            self._walk_directory,
            directory
        )
        
        return video_files
    
    async def _scan_flat(self, directory: Path) -> List[Path]:
        """Scan only the specified directory (non-recursive)"""
        loop = asyncio.get_event_loop()
        
        video_files = await loop.run_in_executor(
            self.executor,
            self._scan_single_directory,
            directory
        )
        
        return video_files
    
    def _walk_directory(self, directory: Path) -> List[Path]:
        """Walk directory tree (runs in thread pool)"""
        video_files = []
        
        try:
            for root, dirs, files in os.walk(directory):
                root_path = Path(root)
                
                # Filter out hidden directories
                dirs[:] = [
                    d for d in dirs 
                    if not d.startswith('.')
                ]
                
                for filename in files:
                    if self._is_video_file(filename):
                        file_path = root_path / filename
                        video_files.append(file_path)
                        
        except PermissionError as e:
            logger.warning(f"Permission denied: {e}")
        except Exception as e:
            logger.error(f"Error walking directory {directory}: {e}")
        
        return video_files
    
    def _scan_single_directory(self, directory: Path) -> List[Path]:
        """Scan single directory without recursion"""
        video_files = []
        
        try:
            for item in directory.iterdir():
                if item.is_file() and self._is_video_file(item.name):
                    video_files.append(item)
        except PermissionError as e:
            logger.warning(f"Permission denied: {e}")
        except Exception as e:
            logger.error(f"Error scanning directory {directory}: {e}")
        
        return video_files
    
    def _is_video_file(self, filename: str) -> bool:
        """Check if filename matches video extensions"""
        extension = Path(filename).suffix.lower().lstrip('.')
        return extension in self.extensions
    
    def is_video_file(self, file_path: Path) -> bool:
        """Public method to check if file is a video"""
        return file_path.is_file() and self._is_video_file(file_path.name)
    
    @staticmethod
    def _is_network_path(path: Path) -> bool:
        r"""
        Detect if path is on network storage
        
        Detects:
        - Windows UNC paths (\\server\share)
        - Linux/Mac NFS mounts (/mnt/, /media/)
        - SMB mounts
        """
        path_str = str(path.absolute())
        
        # Windows UNC paths
        if path_str.startswith('\\\\') or path_str.startswith('//'):
            return True
        
        # Linux/Mac network mount points
        network_indicators = ['/mnt/', '/media/', '/net/', '/Network/']
        if any(indicator in path_str for indicator in network_indicators):
            return True
        
        # Check if path is on network filesystem (Linux)
        try:
            import subprocess
            result = subprocess.run(
                ['df', '-T', path_str],
                capture_output=True,
                text=True,
                timeout=2
            )
            # Check for network filesystem types
            network_fs = ['nfs', 'cifs', 'smb', 'afs']
            if any(fs in result.stdout.lower() for fs in network_fs):
                return True
        except:
            pass
        
        return False
    
    def get_directory_stats(self, directory: Path) -> dict:
        """
        Get statistics about a directory
        
        Returns:
            Dict with file counts, total size, etc.
        """
        stats = {
            'total_files': 0,
            'video_files': 0,
            'total_size': 0,
            'video_size': 0,
            'largest_file': None,
            'largest_size': 0
        }
        
        try:
            for item in directory.rglob('*'):
                if item.is_file():
                    stats['total_files'] += 1
                    file_size = item.stat().st_size
                    stats['total_size'] += file_size
                    
                    if self._is_video_file(item.name):
                        stats['video_files'] += 1
                        stats['video_size'] += file_size
                        
                        if file_size > stats['largest_size']:
                            stats['largest_size'] = file_size
                            stats['largest_file'] = item
        except Exception as e:
            logger.error(f"Error getting directory stats: {e}")
        
        return stats
    
    def __del__(self):
        """Cleanup executor on deletion"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)