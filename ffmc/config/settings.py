# ffmc/config/settings.py - FIXED VERSION
"""
Configuration management with validation
"""

import yaml
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field, asdict
from ffmc.utils.exceptions import ConfigurationError


@dataclass
class VideoQualitySettings:
    """Video quality configuration"""
    crf: int = 23
    preset: str = "medium"
    tune: Optional[str] = "film"
    
    def validate(self):
        if not 0 <= self.crf <= 51:
            raise ConfigurationError(f"CRF must be between 0-51, got {self.crf}")
        
        valid_presets = [
            "ultrafast", "superfast", "veryfast", "faster", 
            "fast", "medium", "slow", "slower", "veryslow"
        ]
        if self.preset not in valid_presets:
            raise ConfigurationError(
                f"Invalid preset '{self.preset}'. "
                f"Valid options: {', '.join(valid_presets)}"
            )


@dataclass
class AudioQualitySettings:
    """Audio quality configuration"""
    bitrate: str = "192k"
    codec: str = "aac"
    
    def validate(self):
        # Validate bitrate format
        if not self.bitrate.endswith('k'):
            raise ConfigurationError(f"Invalid bitrate format: {self.bitrate}")


@dataclass
class HardwareAcceleration:
    """Hardware acceleration settings"""
    enabled: bool = False
    type: str = "nvidia"
    encoder: str = "hevc_nvenc"
    
    def validate(self):
        valid_types = ["nvidia", "amd", "intel", "videotoolbox"]
        if self.enabled and self.type not in valid_types:
            raise ConfigurationError(
                f"Invalid GPU type '{self.type}'. "
                f"Valid options: {', '.join(valid_types)}"
            )


@dataclass
class Settings:
    """Main application settings"""
    
    # Codecs
    target_video_codec: str = "hevc"
    target_audio_codec: str = "aac"
    
    # Quality
    video_quality: VideoQualitySettings = field(default_factory=VideoQualitySettings)
    audio_quality: AudioQualitySettings = field(default_factory=AudioQualitySettings)
    
    # Performance
    concurrent_conversions: int = 2
    cpu_affinity: bool = True
    
    # Behavior
    skip_if_larger: bool = True
    create_backup: bool = False
    output_suffix: str = ""
    output_directory: Optional[Path] = None
    
    # File handling
    extensions: List[str] = field(default_factory=lambda: [
        "avi", "mp4", "mkv", "mov", "wmv", "flv", "webm",
        "m4v", "mpg", "mpeg", "3gp", "ogv", "ts", "vob"
    ])
    
    # Hardware
    hardware_acceleration: HardwareAcceleration = field(
        default_factory=HardwareAcceleration
    )
    
    # Paths
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    
    # Notifications
    webhook_url: Optional[str] = None
    
    # Database
    database_path: Path = Path("data/conversions.db")
    state_file: Path = Path("data/state.pkl")
    
    @classmethod
    def load(
        cls,
        config_path: Optional[Path] = None,
        profile: str = "balanced"
    ) -> "Settings":
        """Load settings from file and apply profile"""
        
        # Default config path
        if config_path is None:
            config_path = Path("config/default.yaml")
        
        # Load base configuration
        if config_path.exists():
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f) or {}
        else:
            config_data = {}
        
        # Load and apply profile
        profile_path = Path("config/profiles.yaml")
        if profile_path.exists() and profile != "balanced":
            with open(profile_path, 'r') as f:
                profiles = yaml.safe_load(f) or {}
                if profile in profiles:
                    # Deep merge profile into config
                    _deep_merge(config_data, profiles[profile])
        
        # Convert nested dicts to dataclass instances
        try:
            # Handle video_quality
            if 'video_quality' in config_data and isinstance(config_data['video_quality'], dict):
                config_data['video_quality'] = VideoQualitySettings(**config_data['video_quality'])
            
            # Handle audio_quality
            if 'audio_quality' in config_data and isinstance(config_data['audio_quality'], dict):
                config_data['audio_quality'] = AudioQualitySettings(**config_data['audio_quality'])
            
            # Handle hardware_acceleration
            if 'hardware_acceleration' in config_data and isinstance(config_data['hardware_acceleration'], dict):
                config_data['hardware_acceleration'] = HardwareAcceleration(**config_data['hardware_acceleration'])
            
            # Convert Path strings
            if 'output_directory' in config_data and config_data['output_directory']:
                config_data['output_directory'] = Path(config_data['output_directory'])
            if 'database_path' in config_data:
                config_data['database_path'] = Path(config_data['database_path'])
            if 'state_file' in config_data:
                config_data['state_file'] = Path(config_data['state_file'])
            
            # Create settings instance
            settings = cls(**config_data)
            settings.validate()
            return settings
            
        except TypeError as e:
            raise ConfigurationError(f"Invalid configuration: {e}")
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}")
    
    def validate(self):
        """Validate all settings"""
        self.video_quality.validate()
        self.audio_quality.validate()
        self.hardware_acceleration.validate()
        
        if self.concurrent_conversions < 1:
            raise ConfigurationError(
                f"concurrent_conversions must be >= 1, got {self.concurrent_conversions}"
            )
        
        # Ensure data directories exist
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
    
    def save(self, path: Path):
        """Save current settings to file"""
        with open(path, 'w') as f:
            yaml.dump(asdict(self), f, default_flow_style=False)


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Deep merge two dictionaries"""
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base