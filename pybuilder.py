#!/usr/bin/env python3
"""Lanceur de PyBuilder : python pybuilder.py [script.py]"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pybuilder.app import main

if __name__ == "__main__":
    raise SystemExit(main())
