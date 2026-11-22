"""Step 3: the automatic checks (no forecast sees its own race, strategies obey the rules).

In PyCharm: open this file and click the green ▶ arrow below.
"""
from _venv import run

if __name__ == "__main__":
    run("-m", "pytest", "-q", "tests")
