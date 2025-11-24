"""
FFMC - FFmpeg Mass Conversion
Professional async video transcoding framework
"""

__version__ = "1.0.0"
__author__ = "FFMC Contributors"
__license__ = "MIT"

from ffmc.core.orchestrator import ConversionOrchestrator
from ffmc.config.settings import Settings
from ffmc.utils.exceptions import FFMCError

__all__ = [
    "ConversionOrchestrator",
    "Settings",
    "FFMCError",
]