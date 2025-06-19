#!/usr/bin/env python3
"""Quick TURN test that exits after finding key info"""

import subprocess
import threading
import time
import re

def run_test():
    proc = subprocess.Popen([
        'python3', 'publish.py',
        '--room', 'testroom123',
        '--record', 'quick_turn',
        '--record-room',
        '--password', 'false',
        '--noaudio'
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    found_turn = False
    found_error = False
    
    # Read for 5 seconds max
    def read_output():
        nonlocal found_turn, found_error
        for _ in range(50):  # Read up to 50 lines
            line = proc.stdout.readline()
            if not line:
                break
            
            clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
            
            if "Using VDO.Ninja TURN:" in clean:
                print(f"TURN: {clean}")
                if "@" in clean:
                    found_turn = True
                    print("✅ TURN URL includes credentials!")
                else:
                    print("❌ TURN URL missing credentials!")
                    
            if "No username specified" in clean:
                print(f"ERROR: {clean}")
                found_error = True
    
    t = threading.Thread(target=read_output)
    t.start()
    
    # Wait max 5 seconds
    t.join(timeout=5)
    
    # Kill process
    proc.terminate()
    try:
        proc.wait(timeout=1)
    except:
        proc.kill()
    
    return found_turn, found_error

print("Quick TURN configuration test...")
print("=" * 50)

turn_ok, has_error = run_test()

print("\nResults:")
print(f"  TURN configured: {'✅ Yes' if turn_ok else '❌ No'}")
print(f"  Errors found: {'❌ Yes' if has_error else '✅ No'}")

if turn_ok and not has_error:
    print("\n✅ TURN fix appears to be working!")
else:
    print("\n❌ TURN configuration needs more work")