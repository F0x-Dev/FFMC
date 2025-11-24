# ffmc/__main__.py
"""Entry point for python -m ffmc"""
import sys
import asyncio
from ffmc.cli import main

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))