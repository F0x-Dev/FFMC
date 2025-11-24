"""
Custom exceptions for FFMC
"""


class FFMCError(Exception):
    """Base exception for all FFMC errors"""
    pass


class ConfigurationError(FFMCError):
    """Configuration-related errors"""
    pass


class DependencyError(FFMCError):
    """Missing or invalid dependencies"""
    pass


class AnalysisError(FFMCError):
    """Video analysis errors"""
    pass


class ConversionError(FFMCError):
    """Conversion process errors"""
    pass


class ValidationError(FFMCError):
    """Post-conversion validation errors"""
    pass


class FileSystemError(FFMCError):
    """File system operation errors"""
    pass


class DatabaseError(FFMCError):
    """Database operation errors"""
    pass