#!/usr/bin/env python3
"""Minimal test to check if publish.py starts properly"""

import subprocess
import time
import threading

def run_test():
    print("Starting minimal test...")
    proc = subprocess.Popen([
        'python3', 'publish.py',
        '--room', 'test123',
        '--record', 'minimal',
        '--record-room',
        '--password', 'false',
        '--noaudio'
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Read output in thread
    def read_output():
        for line in proc.stdout:
            print(f"OUT: {line.rstrip()}")
    
    def read_error():
        for line in proc.stderr:
            print(f"ERR: {line.rstrip()}")
    
    t1 = threading.Thread(target=read_output)
    t2 = threading.Thread(target=read_error)
    t1.start()
    t2.start()
    
    # Wait 5 seconds
    time.sleep(5)
    
    print("\nTerminating process...")
    proc.terminate()
    proc.wait()
    print(f"Exit code: {proc.returncode}")

if __name__ == "__main__":
    run_test()