#!/usr/bin/env python3
"""
Test script for ensure_R_minimal, maybe_install_R_packages function.
This can be run on a VM to test the environment preparation before a full agent run.

Usage:
    python test_env_prep.py
"""

import sys
import os
import subprocess

from pathlib import Path

# Add the agent directory to the path so we can import main
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from main import ensure_R_minimal, maybe_install_R_packages
except ImportError as e:
    print(f"ERROR: Failed to import ensure_R_minimal, maybe_install_R_packages: {e}")
    print("Make sure you're running this from the agents/core_agent directory")
    sys.exit(1)


def main():
    print("="*80)
    print("Testing ensure_R_minimal + maybe_install_R_packages (CORE Hard env)")
    print("="*80)

    print()
    print("[1] Running ensure_R_minimal...")
    r_report = ensure_R_minimal()
    print("ensure_R_minimal returned:", r_report)

    print()
    print("[2] Running maybe_install_R_packages...")
    pkg_report = maybe_install_R_packages()
    print("maybe_install_R_packages returned:", pkg_report)

    print()
    print("[3] Testing PNG device availability...")
    code, out = subprocess.getstatusoutput('Rscript -e "png(\'/tmp/x.png\'); plot(1:10); dev.off()"')
    print("png device test exit code:", code)
    print("output:", out)

    print()
    print("DONE")

    # this is enough for tester harness to treat as success/fail exit status
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())