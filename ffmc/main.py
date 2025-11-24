"""
Entry point for running FFMC as a module
Usage: python -m ffmc [options]
"""

import sys
import asyncio
from ffmc.cli import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        sys.exit(1)