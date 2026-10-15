"""
Final V2 website entry point.

This wrapper runs the same final supply-comparison and redistribution logic
implemented in 04_supply_comparison.py.
"""

from pathlib import Path
import runpy

SCRIPT = Path(__file__).with_name("04_supply_comparison.py")
runpy.run_path(str(SCRIPT), run_name="__main__")
