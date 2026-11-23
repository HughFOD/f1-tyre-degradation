"""Step 2: download the lap data (first run ~140 MB from GitHub), fit tyre wear for every race,
test the forecasts and the pit strategies, and write results to output/ and charts to docs/img/.
About 3 minutes.

In PyCharm: open this file and click the green ▶ arrow next to `if __name__ == "__main__":`.
"""
from _venv import run

if __name__ == "__main__":
    run("run.py")
    print("\n✅ Done. Read output/summary.json")
