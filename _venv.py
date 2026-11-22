"""Finds the project's Python (made by step1_setup.py) so the step scripts run inside it."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = HERE / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(*args):
    if not PY.exists():
        sys.exit("Run step1_setup.py first (it creates the .venv this project runs in).")
    subprocess.check_call([str(PY), *args], cwd=HERE)
