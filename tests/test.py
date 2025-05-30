"""
Project test script for testing the project different phases.
"""

import os
import shutil
import sys
from pathlib import Path
import subprocess
import argparse

# Add parent directory to path
# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# set working directory to the project root (parent directory of this script directory)
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def main():
    parser = argparse.ArgumentParser(description="Test script for project phases")
    
    parser.add_argument(
        "--phase",
        type=int,
        default=1,
        help="The phase to test (1-7)",
    )
    args = parser.parse_args()  
    
    try:
        # concate tests\test_phase{args.phase}.py
        test_file = f"tests/test_phase{args.phase}.py"
        # run the test file
        subprocess.run(["python", test_file])
    except Exception as e:
        print(f"Error: {e}")
        print(f"Error type: {type(e)}")
if __name__ == "__main__":
    main()
