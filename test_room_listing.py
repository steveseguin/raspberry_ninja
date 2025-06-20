#!/usr/bin/env python3
"""
Test to see what's in the room listing
"""

import subprocess
import time
import re

def run_test():
    print("Testing room listing detection...")
    print("Please make sure you have these URLs open in browser tabs:")
    print("1. https://vdo.ninja/?room=testroom123999999999&push=tUur6fffwt&debug&view")
    print("2. https://vdo.ninja/?room=testroom123999999999&push=tUur6wt&debug&view")
    print("-" * 70)
    
    cmd = [
        'python3', 'publish.py',
        '--room', 'testroom123999999999',
        '--room-ndi',
        '--password', 'false'
    ]
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Look for room listing info
    start_time = time.time()
    room_members = []
    streams_found = 0
    
    while time.time() - start_time < 20:
        line = proc.stdout.readline()
        if not line:
            break
            
        line = line.strip()
        
        # Remove ANSI color codes for easier parsing
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_line = ansi_escape.sub('', line)
        
        # Print relevant lines
        if any(phrase in clean_line for phrase in ['Room has', 'Member', 'Stream:', 'Found', 'UUID=', 'streamID=']):
            print(clean_line)
            
        # Extract member info
        if 'Member' in clean_line and 'UUID=' in clean_line:
            room_members.append(clean_line)
            
        # Check for streams found
        if 'Found' in clean_line and 'streams to record' in clean_line:
            try:
                # Extract number
                parts = clean_line.split('Found')[1].split('streams')[0].strip()
                streams_found = int(parts)
            except:
                pass
    
    proc.terminate()
    proc.wait()
    
    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    print(f"Room members detected: {len(room_members)}")
    for member in room_members:
        print(f"  {member}")
    print(f"Streams to record: {streams_found}")
    
    if streams_found == 0 and room_members:
        print("\n⚠️  Members were detected but no streams were found to record.")
        print("This suggests the members don't have both UUID and streamID.")

if __name__ == "__main__":
    run_test()