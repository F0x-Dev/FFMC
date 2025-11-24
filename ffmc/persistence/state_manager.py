# ffmc/persistence/state_manager.py
"""
State management for resume capability
Stores conversion state to enable resuming interrupted jobs
"""

import pickle
from pathlib import Path
from typing import Dict, Any, List, Set, Optional
from datetime import datetime

from ffmc.monitoring.logger import get_logger
from ffmc.utils.exceptions import FileSystemError

logger = get_logger('state_manager')


class StateManager:
    """
    Manages persistent state for resume capability
    
    Stores:
    - Pending conversions
    - Completed conversions
    - Failed conversions
    - Job metadata
    """
    
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.current_state: Dict[str, Any] = self._default_state()
    
    def _default_state(self) -> Dict[str, Any]:
        """Create default state structure"""
        return {
            'version': 1,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'pending': [],
            'completed': set(),
            'failed': set(),
            'skipped': set(),
            'job_metadata': {}
        }
    
    def load(self) -> Optional[Dict[str, Any]]:
        """
        Load state from file
        
        Returns:
            State dictionary or None if no state exists
        """
        if not self.state_file.exists():
            logger.debug("No state file found")
            return None
        
        try:
            with open(self.state_file, 'rb') as f:
                state = pickle.load(f)
            
            # Validate state structure
            if not isinstance(state, dict) or 'version' not in state:
                logger.warning("Invalid state file, ignoring")
                return None
            
            self.current_state = state
            logger.info(
                f"Loaded state: {len(state.get('pending', []))} pending, "
                f"{len(state.get('completed', set()))} completed"
            )
            return state
            
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return None
    
    def save(self, state: Optional[Dict[str, Any]] = None):
        """
        Save state to file
        
        Args:
            state: State dictionary (uses current_state if None)
        """
        if state is not None:
            self.current_state = state
        
        self.current_state['updated_at'] = datetime.now().isoformat()
        
        try:
            # Write to temporary file first for atomic operation
            temp_file = self.state_file.with_suffix('.tmp')
            with open(temp_file, 'wb') as f:
                pickle.dump(self.current_state, f)
            
            # Atomic replace
            temp_file.replace(self.state_file)
            
            logger.debug("State saved successfully")
            
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            raise FileSystemError(f"Could not save state: {e}")
    
    def mark_completed(self, file_path: Path):
        """
        Mark a file as completed
        
        Args:
            file_path: Path to completed file
        """
        file_str = str(file_path)
        
        # Remove from pending
        if file_str in self.current_state['pending']:
            self.current_state['pending'].remove(file_str)
        
        # Add to completed
        self.current_state['completed'].add(file_str)
        
        # Remove from failed if present
        self.current_state['failed'].discard(file_str)
        
        self.save()
    
    def mark_failed(self, file_path: Path, error: str = ""):
        """
        Mark a file as failed
        
        Args:
            file_path: Path to failed file
            error: Error message
        """
        file_str = str(file_path)
        
        # Remove from pending
        if file_str in self.current_state['pending']:
            self.current_state['pending'].remove(file_str)
        
        # Add to failed with error
        self.current_state['failed'].add(file_str)
        
        # Store error message in metadata
        if 'errors' not in self.current_state['job_metadata']:
            self.current_state['job_metadata']['errors'] = {}
        
        self.current_state['job_metadata']['errors'][file_str] = {
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        
        self.save()
    
    def mark_skipped(self, file_path: Path, reason: str = ""):
        """
        Mark a file as skipped
        
        Args:
            file_path: Path to skipped file
            reason: Reason for skipping
        """
        file_str = str(file_path)
        
        # Remove from pending
        if file_str in self.current_state['pending']:
            self.current_state['pending'].remove(file_str)
        
        # Add to skipped
        self.current_state['skipped'].add(file_str)
        
        # Store reason in metadata
        if 'skipped_reasons' not in self.current_state['job_metadata']:
            self.current_state['job_metadata']['skipped_reasons'] = {}
        
        self.current_state['job_metadata']['skipped_reasons'][file_str] = {
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        }
        
        self.save()
    
    def is_completed(self, file_path: Path) -> bool:
        """Check if file was completed"""
        return str(file_path) in self.current_state.get('completed', set())
    
    def is_failed(self, file_path: Path) -> bool:
        """Check if file failed"""
        return str(file_path) in self.current_state.get('failed', set())
    
    def is_skipped(self, file_path: Path) -> bool:
        """Check if file was skipped"""
        return str(file_path) in self.current_state.get('skipped', set())
    
    def get_pending(self) -> List[str]:
        """Get list of pending files"""
        return self.current_state.get('pending', [])
    
    def get_failed(self) -> Set[str]:
        """Get set of failed files"""
        return self.current_state.get('failed', set())
    
    def get_error_message(self, file_path: Path) -> Optional[str]:
        """Get error message for a failed file"""
        errors = self.current_state.get('job_metadata', {}).get('errors', {})
        file_str = str(file_path)
        
        if file_str in errors:
            return errors[file_str].get('error', '')
        return None
    
    def clear(self):
        """Clear all state"""
        self.current_state = self._default_state()
        self.save()
        logger.info("State cleared")
    
    def delete(self):
        """Delete state file"""
        if self.state_file.exists():
            self.state_file.unlink()
            logger.info("State file deleted")
        self.current_state = self._default_state()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get state statistics"""
        return {
            'total_pending': len(self.current_state.get('pending', [])),
            'total_completed': len(self.current_state.get('completed', set())),
            'total_failed': len(self.current_state.get('failed', set())),
            'total_skipped': len(self.current_state.get('skipped', set())),
            'created_at': self.current_state.get('created_at'),
            'updated_at': self.current_state.get('updated_at')
        }
    
    def export_report(self, output_path: Path):
        """
        Export human-readable report
        
        Args:
            output_path: Path for report file
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("FFMC Conversion State Report\n")
                f.write("=" * 80 + "\n\n")
                
                stats = self.get_statistics()
                f.write(f"Created: {stats['created_at']}\n")
                f.write(f"Updated: {stats['updated_at']}\n\n")
                
                f.write("Summary:\n")
                f.write(f"  Pending: {stats['total_pending']}\n")
                f.write(f"  Completed: {stats['total_completed']}\n")
                f.write(f"  Failed: {stats['total_failed']}\n")
                f.write(f"  Skipped: {stats['total_skipped']}\n\n")
                
                if self.current_state.get('failed'):
                    f.write("Failed Files:\n")
                    f.write("-" * 80 + "\n")
                    errors = self.current_state.get('job_metadata', {}).get('errors', {})
                    for file_path in self.current_state['failed']:
                        error_info = errors.get(file_path, {})
                        error_msg = error_info.get('error', 'Unknown error')
                        timestamp = error_info.get('timestamp', 'Unknown time')
                        f.write(f"{file_path}\n")
                        f.write(f"  Error: {error_msg}\n")
                        f.write(f"  Time: {timestamp}\n\n")
                
                if self.current_state.get('skipped'):
                    f.write("Skipped Files:\n")
                    f.write("-" * 80 + "\n")
                    reasons = self.current_state.get('job_metadata', {}).get('skipped_reasons', {})
                    for file_path in self.current_state['skipped']:
                        reason_info = reasons.get(file_path, {})
                        reason = reason_info.get('reason', 'Unknown reason')
                        f.write(f"{file_path}\n")
                        f.write(f"  Reason: {reason}\n\n")
            
            logger.info(f"State report exported to {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to export report: {e}")
            raise FileSystemError(f"Could not export report: {e}")