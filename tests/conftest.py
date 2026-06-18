"""
Pytest configuration for Lithium IDE tests.
Adds the project root to sys.path so that imports like ``from src.xxx`` work.
"""

import os
import sys

# Ensure the project root (parent of tests/) is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
