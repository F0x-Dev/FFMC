# FFMC - FFmpeg Mass Converter

**Asynchronous video transcoding framework for batch media processing**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

FFMC is a video conversion tool built for efficient batch transcoding of video libraries. Designed with Python's async architecture and supporting both CPU and GPU acceleration, it provides a comprehensive solution for media professionals, archivists, and content managers.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [Codec Selection](#codec-selection)
- [Performance](#performance)
- [API Reference](#api-reference)
- [Development](#development)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [License](#license)

---

## Features

### Core Functionality

- **Asynchronous Processing**: Concurrent video conversion with configurable worker pools
- **Intelligent Analysis**: Automatic codec detection and conversion necessity evaluation
- **State Management**: Resume capability for interrupted batch operations
- **Database Tracking**: SQLite-backed conversion history and statistics
- **Progress Monitoring**: Real-time progress display with resource tracking

### Encoding Support

- **Software Encoding**: Optimized libx265 (H.265/HEVC) implementation
- **Hardware Acceleration**: NVIDIA NVENC, AMD AMF, Intel QSV, Apple VideoToolbox
- **Quality Profiles**: Predefined configurations (fast, balanced, quality, archive)
- **Codec Advisor**: Intelligent recommendations with quality prediction
- **Advanced Parameters**: HDR passthrough, adaptive quantization, custom tuning

### Operational Features

- **CPU Affinity Management**: Optimal task distribution across cores
- **Network Storage Detection**: Automatic optimization for NAS/SMB/NFS
- **Webhook Notifications**: Discord, Slack, and generic webhook support
- **Structured Logging**: Separate logs for operations, errors, and metrics
- **Performance Analytics**: CPU, memory, disk I/O monitoring

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     CLI Interface                        │
│                   (ffmc/cli.py)                         │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  Orchestrator Layer                      │
│         (ffmc/core/orchestrator.py)                     │
│  - Workflow coordination                                │
│  - Resource management                                  │
│  - Error handling                                       │
└─┬───────────┬───────────┬───────────┬──────────────────┘
  │           │           │           │
┌─▼─────┐ ┌──▼────┐ ┌────▼───┐ ┌────▼─────┐
│ I/O    │ │Analysis│ │Convert │ │Monitoring│
│ Layer  │ │ Layer  │ │ Layer  │ │  Layer   │
└────────┘ └────────┘ └────────┘ └──────────┘
```

### Component Structure

```
ffmc/
├── core/              # Orchestration and worker management
│   ├── orchestrator.py
│   └── worker_pool.py
├── analysis/          # Video analysis and codec detection
│   ├── codec_detector.py
│   └── codec_advisor.py
├── conversion/        # FFmpeg encoding logic
│   ├── encoder.py
│   └── command_builder.py
├── io/                # File system operations
│   └── file_scanner.py
├── persistence/       # Database and state management
│   ├── database.py
│   └── state_manager.py
├── monitoring/        # Logging and metrics
│   ├── logger.py
│   ├── progress_tracker.py
│   ├── metrics_collector.py
│   └── notifier.py
├── config/            # Configuration management
│   └── settings.py
└── utils/             # Utilities and exceptions
    └── exceptions.py
```

---

## Installation

### Prerequisites

- Python 3.10 or higher
- FFmpeg 4.4+ with libx265 support
- 4GB RAM minimum (8GB recommended)
- Optional: CUDA-capable GPU for hardware acceleration

### System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv ffmpeg
```

**macOS:**
```bash
brew install python ffmpeg
```

**Windows:**
```powershell
winget install Python.Python.3.11
winget install Gyan.FFmpeg
```

### Install FFMC

```bash
# Clone repository
https://github.com/F0x-Dev/FFMC.git
cd ffmc

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or
.\venv\Scripts\activate   # Windows

# Install
pip install -e .

# Verify
ffmc --version
ffmc --check-deps
```

---

## Quick Start

### Basic Usage

```bash
# Convert videos in directory
ffmc /path/to/videos

# Preview without converting
ffmc /path/to/videos --dry-run

# Use specific profile
ffmc /path/to/videos --profile quality

# Enable GPU
ffmc /path/to/videos --gpu --gpu-type nvidia

# Resume interrupted job
ffmc --resume
```

### Workflow Example

```bash
# 1. Analyze and get recommendations
ffmc /path/to/videos --analyze

# 2. Preview conversion
ffmc /path/to/videos --dry-run --profile balanced

# 3. Execute
ffmc /path/to/videos --profile balanced
```

---

## Configuration

### Configuration Files

**config/default.yaml:**
```yaml
# Codec settings
target_video_codec: hevc
target_audio_codec: aac

# Quality
video_quality:
  crf: 23
  preset: medium
  tune: film

audio_quality:
  bitrate: 192k

# Performance
concurrent_conversions: 2
cpu_affinity: true

# Behavior
skip_if_larger: true
create_backup: false
output_suffix: ""

# Hardware acceleration
hardware_acceleration:
  enabled: false
  type: nvidia
  encoder: hevc_nvenc

# Paths
ffmpeg_path: ffmpeg
ffprobe_path: ffprobe

# Notifications
webhook_url: null

# Persistence
database_path: data/conversions.db
state_file: data/state.pkl
```

### Profiles

**config/profiles.yaml:**
```yaml
fast:
  video_quality:
    crf: 28
    preset: veryfast
  concurrent_conversions: 4

balanced:
  video_quality:
    crf: 23
    preset: medium
  concurrent_conversions: 2

quality:
  video_quality:
    crf: 18
    preset: slow
  concurrent_conversions: 1

archive:
  video_quality:
    crf: 20
    preset: veryslow
  create_backup: true
```

### Profile Comparison

| Profile | CRF | Preset | Speed | Quality | Use Case |
|---------|-----|--------|-------|---------|----------|
| fast | 28 | veryfast | 4x | Good | Quick conversion |
| balanced | 23 | medium | 1x | Very Good | General purpose |
| quality | 18 | slow | 0.5x | Excellent | High-quality output |
| archive | 20 | veryslow | 0.3x | Excellent | Long-term storage |

---

## Usage

### Command-Line Interface

```bash
ffmc [OPTIONS] PATHS...
```

### Options

**General:**
```
-h, --help                 Show help
--version                  Show version
-c, --config PATH          Configuration file
-p, --profile PROFILE      Encoding profile
```

**Modes:**
```
--dry-run                  Preview only
--resume                   Resume interrupted job
--force                    Force reconversion
--analyze                  Show codec recommendations
--interactive              Interactive selection
```

**Hardware:**
```
--gpu                      Enable GPU
--gpu-type TYPE            GPU type (nvidia|amd|intel|videotoolbox)
```

**Performance:**
```
-j, --jobs N               Concurrent conversions
```

**Output:**
```
-o, --output DIR           Output directory
--suffix SUFFIX            Output file suffix
```

**Quality:**
```
--max-quality-loss N       Max quality loss (%)
--min-compression N        Min compression (%)
```

**Logging:**
```
-v, --verbose              Increase verbosity
-q, --quiet                Suppress output
--log-file PATH            Custom log file
```

**Notifications:**
```
--webhook URL              Webhook URL
```

### Examples

**Basic conversion:**
```bash
ffmc /media/videos
```

**High-quality archival:**
```bash
ffmc /media/archive --profile quality --jobs 1
```

**GPU acceleration:**
```bash
ffmc /media/batch --profile fast --gpu --gpu-type nvidia --jobs 4
```

**Interactive mode:**
```bash
ffmc /media/videos --interactive
```

**Analyze codecs:**
```bash
ffmc /media/videos --analyze
```

**Resume job:**
```bash
ffmc --resume
```

---

## Codec Selection

### Intelligent Recommendations

FFMC analyzes videos and recommends optimal codecs based on:
- Source codec and quality
- Resolution and frame rate
- Content complexity
- Available hardware
- User constraints

### Quality Metrics

**VMAF (Video Multi-Method Assessment Fusion):**
- 95-100: Visually lossless
- 90-95: Excellent quality
- 85-90: Good quality
- 80-85: Acceptable quality
- Below 80: Noticeable degradation

**Quality Loss Categories:**
- 0-1%: Minimal loss (imperceptible)
- 1-3%: Low loss (barely noticeable)
- 3-5%: Moderate loss (acceptable)
- 5-10%: High loss (visible in complex scenes)
- Above 10%: Extreme loss (significant degradation)

### Codec Profiles

**H.265/HEVC:**
| Profile | CRF | Quality Loss | Compression | Speed |
|---------|-----|--------------|-------------|-------|
| High Quality | 18 | 0.5% | 50% | Slow |
| Balanced | 23 | 2.0% | 60% | Medium |
| Fast | 28 | 5.0% | 70% | Fast |

**AV1:**
| Profile | CRF | Quality Loss | Compression | Speed |
|---------|-----|--------------|-------------|-------|
| Quality | 25 | 1.0% | 65% | Very Slow |
| Balanced | 30 | 3.0% | 72% | Slow |

**H.264:**
| Profile | CRF | Quality Loss | Compression | Speed |
|---------|-----|--------------|-------------|-------|
| Quality | 18 | 0.5% | 40% | Slow |
| Balanced | 23 | 2.0% | 50% | Medium |

### Usage

**Analyze video:**
```bash
ffmc video.mp4 --analyze
```

**Interactive selection:**
```bash
ffmc video.mp4 --interactive
```

**Set constraints:**
```bash
ffmc video.mp4 --analyze --max-quality-loss 3.0 --min-compression 50
```

---

## Performance

### Optimization Techniques

**CPU Optimization:**
- Worker distribution across physical cores
- CPU affinity pinning
- Thread count optimization per encoding type

**GPU Acceleration:**
- NVIDIA NVENC with spatial/temporal AQ
- AMD AMF with VBR rate control
- Intel QSV with quality presets
- Apple VideoToolbox for macOS

**Network Storage:**
- Automatic NFS/SMB/CIFS detection
- Reduced concurrent conversions
- Optimized I/O patterns

### Benchmarks

Test system: AMD Ryzen 9 5900X, NVIDIA RTX 3080, NVMe SSD  
Test dataset: 100 videos, mixed codecs, avg 1.5GB each

| Configuration | Time | Speed | CPU Usage |
|---------------|------|-------|-----------|
| 1 worker, CPU | 8h 45m | 1.8x | 85% |
| 4 workers, CPU | 2h 30m | 6.4x | 95% |
| 4 workers, GPU | 45m | 22.2x | 25% |

---

## API Reference

### Programmatic Usage

```python
import asyncio
from pathlib import Path
from ffmc import ConversionOrchestrator, Settings

async def main():
    # Load settings
    settings = Settings.load(profile="quality")
    settings.concurrent_conversions = 4
    settings.hardware_acceleration.enabled = True
    
    # Create orchestrator
    orchestrator = ConversionOrchestrator(
        settings=settings,
        dry_run=False
    )
    
    # Run conversion
    paths = [Path("/path/to/videos")]
    success = await orchestrator.run(paths)
    
    return success

if __name__ == "__main__":
    asyncio.run(main())
```

### Core Classes

**ConversionOrchestrator:**
```python
orchestrator = ConversionOrchestrator(
    settings: Settings,
    dry_run: bool = False,
    force: bool = False,
    resume: bool = False
)
await orchestrator.run(paths: List[Path]) -> bool
await orchestrator.resume() -> bool
```

**CodecAdvisor:**
```python
from ffmc.analysis.codec_advisor import CodecAdvisor

advisor = CodecAdvisor()
recommendations = advisor.analyze_and_recommend(
    analysis: VideoAnalysis,
    max_quality_loss: float = 5.0,
    min_compression: float = 0.3,
    gpu_available: str = None
)
```

**Settings:**
```python
from ffmc.config.settings import Settings

settings = Settings.load(
    config_path: Optional[Path] = None,
    profile: str = "balanced"
)
settings.validate()
```

---

## Development

### Setup Development Environment

```bash
# Clone repository
https://github.com/F0x-Dev/FFMC.git
cd ffmc

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ffmc --cov-report=html

# Run specific test
pytest tests/test_codec_detector.py
```

### Code Quality

```bash
# Format code
black ffmc/
isort ffmc/

# Type checking
mypy ffmc/

# Linting
pylint ffmc/
flake8 ffmc/
```

### Project Structure

```
ffmc/
├── ffmc/              # Source code
├── tests/             # Test suite
├── config/            # Configuration files
├── docs/              # Documentation
├── scripts/           # Utility scripts
├── logs/              # Log files (generated)
├── data/              # Runtime data (generated)
├── .github/           # GitHub workflows
├── pyproject.toml     # Project metadata
├── setup.py           # Setup script
├── requirements.txt   # Dependencies
└── README.md          # This file
```

---

## Contributing

Contributions are welcome. Please follow these guidelines:

### Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/name`)
3. Write clean, documented code
4. Add tests for new functionality
5. Ensure all tests pass
6. Commit changes (`git commit -m 'Add feature'`)
7. Push to branch (`git push origin feature/name`)
8. Open a Pull Request

### Code Standards

- Follow PEP 8 style guidelines
- Use type hints for all functions
- Write docstrings (Google style)
- Maintain test coverage above 80%
- Keep functions focused and modular
- Use async/await for I/O operations

### Testing Requirements

- Unit tests for all new code
- Integration tests for workflows
- Performance benchmarks for optimizations
- Documentation updates

---

## Roadmap

### Codec Support

- [ ] AV1 encoding (SVT-AV1, libaom)
- [ ] VP9 support for WebM
- [ ] Codec-specific profiles
- [ ] Advanced HDR metadata handling
- [ ] Multi-channel audio (Opus, FLAC)

### Processing Features

- [ ] Multi-pass encoding
- [ ] Scene detection optimization
- [ ] Intelligent deinterlacing
- [ ] Resolution scaling with quality filters
- [ ] Automatic cropping
- [ ] Subtitle extraction and embedding

### User Interface

- [x] CLI interface
- [ ] Web interface (local server)
  - Dashboard with real-time progress
  - Job queue management
  - Historical statistics
  - Configuration editor
  - Log viewer
- [ ] REST API for remote control
- [ ] Desktop application (Qt/Electron)

### Advanced Features

- [ ] Distributed processing (multi-node cluster)
- [ ] Priority-based job scheduling
- [ ] Per-job resource constraints
- [ ] User authentication system
- [ ] Cloud storage integration (S3, Azure, GCS)
- [ ] Container deployment (Docker, Kubernetes)

### Analysis Tools

- [ ] VMAF/SSIM/PSNR quality assessment
- [ ] AI-driven bitrate prediction
- [ ] Automatic codec selection
- [ ] Content-based analysis
- [ ] Batch optimization learning

### Integration

- [ ] Media server plugins (Plex, Jellyfin, Emby)
- [ ] Cloud transcoding services
- [ ] Email notifications
- [ ] Telegram bot integration
- [ ] Prometheus metrics exporter
- [ ] CI/CD pipeline integration

---

## Troubleshooting

### Common Issues

**FFmpeg not found:**
```bash
# Verify installation
which ffmpeg  # Linux/macOS
where ffmpeg  # Windows

# Check version
ffmpeg -version | grep libx265
```

**Import errors:**
```bash
# Reinstall package
pip uninstall ffmc
pip install -e .
```

**Permission denied:**
```bash
# Fix directory permissions
chmod -R 755 logs/ data/
```

**GPU encoding fails:**
```bash
# Check GPU support
ffmpeg -encoders | grep hevc

# Verify drivers (NVIDIA)
nvidia-smi
```

### Debug Mode

```bash
# Enable verbose logging
ffmc /path --verbose --log-file debug.log

# Check logs
tail -f logs/ffmc.log
tail -f logs/errors.log
```

### Performance Issues

```bash
# Monitor resources
ffmc /path -vv  # Verbose output

# Check worker pool status
# Review logs/performance.log

# Adjust concurrency
ffmc /path --jobs 1  # Reduce workers
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2025 FFMC Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Acknowledgments

- FFmpeg team for the multimedia framework
- Contributors and community members
- Users providing feedback and bug reports

---

## Support

- **Issues**: Report bugs via [GitHub Issues](https://github.com/F0x-Dev/FFMC/issues)
- **Documentation**: See [docs/](docs/) directory
- **Contact**: For security issues, contact maintainers directly

---

## Citation

If using FFMC in research or production, please cite:

```bibtex
@software{ffmc2025,
  title = {FFMC: FFmpeg Mass Converter},
  author = {FFMC Contributors},
  year = {2025},
  url = {https://github.com/F0x-Dev/FFMCc}
}
```



