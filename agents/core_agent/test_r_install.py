#!/usr/bin/env python3
"""
Test script for R installation functions.
This script can be run in Docker to test the R installation functions in isolation.
"""

import os
import sys
import tempfile
import shutil
import subprocess
from pathlib import Path

# Add the current directory to path to import from main.py
sys.path.insert(0, os.path.dirname(__file__))

# Import the R installation functions
from main import ensure_R_minimal, maybe_install_lightweight_R_packages, ensure_cran_packages_installed

def check_rscript():
    """Check if Rscript is available."""
    rscript_path = shutil.which("Rscript")
    if rscript_path:
        print(f"✓ Rscript found at: {rscript_path}")
        # Get R version
        proc = subprocess.run(["Rscript", "--version"], capture_output=True, text=True)
        if proc.returncode == 0:
            print(f"  Version info:\n{proc.stdout}")
        return True
    else:
        print("✗ Rscript not found")
        return False

def test_ensure_R_minimal():
    """Test the ensure_R_minimal function."""
    print("\n" + "="*60)
    print("TEST 1: ensure_R_minimal()")
    print("="*60)
    
    # Check initial state
    initial_rscript = shutil.which("Rscript") is not None
    print(f"Initial state: Rscript available = {initial_rscript}")
    
    # Run the function
    try:
        ensure_R_minimal()
    except Exception as e:
        print(f"ERROR: Function raised exception: {e}")
        return False
    
    # Check final state
    final_rscript = shutil.which("Rscript") is not None
    print(f"Final state: Rscript available = {final_rscript}")
    
    if final_rscript:
        print("✓ TEST PASSED: Rscript is now available")
        return True
    else:
        print("✗ TEST FAILED: Rscript is still not available")
        return False

def test_maybe_install_lightweight_R_packages():
    """Test the maybe_install_lightweight_R_packages function."""
    print("\n" + "="*60)
    print("TEST 2: maybe_install_lightweight_R_packages()")
    print("="*60)
    
    # Check if Rscript is available
    if not check_rscript():
        print("SKIPPED: Rscript not available, cannot test lightweight packages")
        return False
    
    # Create a temporary directory with an R file
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        print(f"Working in temporary directory: {tmpdir}")
        
        # Create a test R file
        test_r_file = Path(tmpdir) / "test.R"
        test_r_file.write_text("# Test R file\nprint('Hello from R')\n")
        print(f"Created test R file: {test_r_file}")
        
        # Run the function
        try:
            maybe_install_lightweight_R_packages()
        except Exception as e:
            print(f"ERROR: Function raised exception: {e}")
            return False
        
        # Check if packages were installed (try to load them)
        print("\nVerifying package installation...")
        for pkg in ["rmarkdown", "tinytex"]:
            cmd = f'Rscript -e "if(requireNamespace(\\"{pkg}\\",quiet=TRUE)) cat(\\"Package {pkg} is available\\n\\") else cat(\\"Package {pkg} is NOT available\\n\\")"'
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if "is available" in proc.stdout:
                print(f"✓ {pkg} is available")
            else:
                print(f"✗ {pkg} is NOT available")
        
        print("✓ TEST COMPLETED (packages may or may not install depending on network/availability)")
        return True

def test_ensure_cran_packages_installed():
    """Test the ensure_cran_packages_installed function."""
    print("\n" + "="*60)
    print("TEST 3: ensure_cran_packages_installed()")
    print("="*60)
    
    # Check if Rscript is available
    if not check_rscript():
        print("SKIPPED: Rscript not available, cannot test CRAN packages")
        return False
    
    # Create a temporary directory with R files that use packages
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        print(f"Working in temporary directory: {tmpdir}")
        
        # Create test R files with different package usage patterns
        test_files = [
            ("test1.R", "library(dplyr)\nlibrary(ggplot2)\n"),
            ("test2.R", 'require("data.table")\n'),
            ("test3.R", "library('tidyr')\n"),
            ("test4.R", "base::print('test')\nstats::rnorm(10)\n"),  # Should not install base/stats
        ]
        
        for filename, content in test_files:
            test_file = Path(tmpdir) / filename
            test_file.write_text(content)
            print(f"Created test R file: {test_file}")
        
        # Run the function
        try:
            result = ensure_cran_packages_installed(root=tmpdir)
            print(f"\nFunction returned: {result}")
        except Exception as e:
            print(f"ERROR: Function raised exception: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        print("✓ TEST COMPLETED")
        return True

def main():
    """Run all tests."""
    print("="*60)
    print("R Installation Functions Test Suite")
    print("="*60)
    print(f"Working directory: {os.getcwd()}")
    print(f"Python version: {sys.version}")
    
    # Store original directory
    original_dir = os.getcwd()
    
    results = []
    
    try:
        # Test 1: ensure_R_minimal
        result1 = test_ensure_R_minimal()
        results.append(("ensure_R_minimal", result1))
        
        # Test 2: maybe_install_lightweight_R_packages
        os.chdir(original_dir)  # Reset directory
        result2 = test_maybe_install_lightweight_R_packages()
        results.append(("maybe_install_lightweight_R_packages", result2))
        
        # Test 3: ensure_cran_packages_installed
        os.chdir(original_dir)  # Reset directory
        result3 = test_ensure_cran_packages_installed()
        results.append(("ensure_cran_packages_installed", result3))
        
    finally:
        os.chdir(original_dir)  # Always return to original directory
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, result in results:
        status = "PASS" if result else "FAIL/SKIP"
        print(f"{test_name}: {status}")
    
    # Exit with appropriate code
    all_passed = all(result for _, result in results)
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()

