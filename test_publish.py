#!/usr/bin/env python3
"""
Simple test to debug video bitrate issue
"""

import subprocess
import sys
import time

def test_publish():
    print("Testing publish to stream 5566281...")
    
    # Run the publish command with test source
    cmd = [
        sys.executable, 
        "publish.py",
        "--test",
        "--streamid", "5566281",
        "--password", "false",  # Disable encryption for testing
        "--debug"  # Enable debug output
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print("Check https://vdo.ninja/?view=5566281&password=false")
    print("-" * 60)
    
    try:
        # Run the command
        process = subprocess.Popen(cmd)
        
        # Let it run for a while
        print("\nLetting it run for 30 seconds to collect stats...")
        time.sleep(30)
        
        print("\nStopping...")
        process.terminate()
        process.wait()
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        if process:
            process.terminate()
            process.wait()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_publish()