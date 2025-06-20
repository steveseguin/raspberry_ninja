#!/usr/bin/env python3
"""
Debug room NDI with detailed output capture
"""

import subprocess
import time
import sys
import os
import threading

def capture_output(process, output_list):
    """Capture process output in a thread"""
    for line in iter(process.stdout.readline, ''):
        if line:
            output_list.append(line.strip())

def main():
    print("Starting room NDI debug test...")
    print("=" * 70)
    
    # Run for 20 seconds
    cmd = [
        'timeout', '20',
        'python3', 'publish.py',
        '--room', 'testroom123999999999',
        '--room-ndi',
        '--password', 'false'
    ]
    
    output_lines = []
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Start output capture thread
    thread = threading.Thread(target=capture_output, args=(process, output_lines))
    thread.daemon = True
    thread.start()
    
    # Wait for process to complete
    process.wait()
    
    # Analyze output
    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    
    # Key indicators
    ndi_mentions = [line for line in output_lines if 'ndi' in line.lower()]
    subprocess_mentions = [line for line in output_lines if 'subprocess' in line.lower()]
    errors = [line for line in output_lines if 'error' in line.lower()]
    combiner_mentions = [line for line in output_lines if 'combiner' in line.lower()]
    stream_mentions = [line for line in output_lines if 'stream' in line.lower() and 'ndi' in line.lower()]
    
    print(f"Total lines captured: {len(output_lines)}")
    print(f"NDI mentions: {len(ndi_mentions)}")
    print(f"Subprocess mentions: {len(subprocess_mentions)}")
    print(f"Combiner mentions: {len(combiner_mentions)}")
    print(f"Errors: {len(errors)}")
    
    if ndi_mentions:
        print("\nNDI-related output:")
        for line in ndi_mentions[:10]:
            print(f"  - {line}")
    
    if errors:
        print("\nErrors found:")
        for line in errors[:10]:
            print(f"  - {line}")
    
    if subprocess_mentions:
        print("\nSubprocess-related output:")
        for line in subprocess_mentions[:10]:
            print(f"  - {line}")
    
    # Save full output
    with open('room_ndi_debug_output.txt', 'w') as f:
        f.write('\n'.join(output_lines))
    print(f"\nFull output saved to room_ndi_debug_output.txt")

if __name__ == "__main__":
    main()