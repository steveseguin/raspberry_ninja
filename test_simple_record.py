#!/usr/bin/env python3
"""Simple test with timeout and better error handling"""

import subprocess
import time
import os
import signal
import select

print("Starting simple recording test with better debugging...")
print("=" * 70)

# Set environment for more debug output
env = os.environ.copy()
env['PYTHONUNBUFFERED'] = '1'

# Start process with explicit timeout handling
proc = subprocess.Popen([
    'python3', '-u', 'publish.py',
    '--room', 'testroom123',
    '--view', 'test_stream',
    '--record', 'debug_test',
    '--password', 'false',
    '--noaudio',
    '--novideo'  # Simplest case - no media
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=0, env=env)

# Set up timeout
def timeout_handler(signum, frame):
    print("\n⏰ Timeout reached, terminating process...")
    proc.terminate()
    time.sleep(1)
    if proc.poll() is None:
        proc.kill()

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(10)  # 10 second timeout

try:
    # Read both stdout and stderr
    while proc.poll() is None:
        readable, _, _ = select.select([proc.stdout, proc.stderr], [], [], 0.1)
        
        for stream in readable:
            line = stream.readline()
            if line:
                if stream == proc.stderr:
                    print(f"STDERR: {line.rstrip()}")
                else:
                    print(f"STDOUT: {line.rstrip()}")
    
    # Get any remaining output
    stdout, stderr = proc.communicate()
    if stdout:
        print(f"FINAL STDOUT: {stdout}")
    if stderr:
        print(f"FINAL STDERR: {stderr}")
        
except Exception as e:
    print(f"Error: {e}")
finally:
    signal.alarm(0)  # Cancel alarm
    if proc.poll() is None:
        proc.terminate()
    
print(f"\nExit code: {proc.returncode}")