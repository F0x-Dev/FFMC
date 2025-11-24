from setuptools import setup, find_packages

setup(
    name="ffmc",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "psutil>=5.9.0",
        "pyyaml>=6.0",
        "rich>=13.0.0",
        "aiohttp>=3.9.0"
    ],
    entry_points={
        "console_scripts": [
            "ffmc=ffmc.cli:main",
        ],
    },
    python_requires=">=3.10",
)