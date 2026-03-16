"""Auto-version the dashboard.

Usage:
    python scripts/save_dashboard_version.py

What it does:
  1. Reads the current app/dashboard.py
  2. Finds the next version number (v2, v3, ...)
  3. Copies the file to versions/dashboard_vN.py
  4. Makes a git commit and tag: dashboard-vN
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DASHBOARD_SRC = ROOT / "app" / "dashboard.py"
VERSIONS_DIR = ROOT / "versions"


def next_version() -> int:
    """Find the highest existing vN and return N+1."""
    VERSIONS_DIR.mkdir(exist_ok=True)
    existing = [p.name for p in VERSIONS_DIR.glob("dashboard_v*.py")]
    nums = []
    for name in existing:
        m = re.search(r"dashboard_v(\d+)\.py", name)
        if m:
            nums.append(int(m.group(1)))
    # Also check git tags
    result = subprocess.run(
        ["git", "tag", "--list", "dashboard-v*"],
        capture_output=True, text=True, cwd=ROOT,
    )
    for tag in result.stdout.splitlines():
        m = re.search(r"dashboard-v(\d+)", tag)
        if m:
            nums.append(int(m.group(1)))
    return max(nums, default=0) + 1


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    if result.stdout.strip():
        print(result.stdout.strip())


def main() -> None:
    if not DASHBOARD_SRC.exists():
        print(f"ERROR: {DASHBOARD_SRC} not found", file=sys.stderr)
        sys.exit(1)

    v = next_version()
    dest = VERSIONS_DIR / f"dashboard_v{v}.py"

    shutil.copy2(DASHBOARD_SRC, dest)
    print(f"Saved → {dest.relative_to(ROOT)}")

    # Stage and commit
    run(["git", "add", str(dest), str(DASHBOARD_SRC)])
    run([
        "git", "commit", "-m",
        f"dashboard v{v} snapshot\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>",
    ])
    run(["git", "tag", f"dashboard-v{v}"])
    print(f"Tagged: dashboard-v{v}")


if __name__ == "__main__":
    main()
