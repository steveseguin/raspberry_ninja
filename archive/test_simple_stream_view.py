#!/usr/bin/env python3
"""Test viewing a single stream to understand the flow"""

import asyncio
import sys

async def test_single_stream():
    """Test viewing a single stream"""
    print("Testing single stream viewing...")
    
    # Use --view mode to receive a single stream
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--view', 'tUur6wt',  # View specific stream
        '--room', 'testroom123999999999',
        '--password', 'false',
        '--save',  # Save to file
        '--debug',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    print("Viewer started, monitoring for 60 seconds...\n")
    
    important_events = []
    start_time = asyncio.get_event_loop().time()
    
    while asyncio.get_event_loop().time() - start_time < 60:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
            if line:
                decoded = line.decode().strip()
                
                # Look for important messages
                if any(keyword in decoded for keyword in [
                    "New pad", "Media offer", "Data-channel", "transceiver",
                    "Recording", "handle_", "bytes", "ERROR", "ICE connection"
                ]):
                    elapsed = int(asyncio.get_event_loop().time() - start_time)
                    print(f"[{elapsed}s] {decoded}")
                    important_events.append((elapsed, decoded))
                    
        except asyncio.TimeoutError:
            pass
    
    print("\nStopping viewer...")
    process.terminate()
    await process.wait()
    
    print("\n=== Important Events ===")
    for elapsed, event in important_events[-20:]:  # Show last 20 events
        print(f"[{elapsed}s] {event}")
    
    # Check for output files
    print("\n=== Output Files ===")
    import glob
    import os
    
    files = glob.glob("*tUur6wt*.webm") + glob.glob("*tUur6wt*.mkv") + glob.glob("*tUur6wt*.ts")
    for f in sorted(files)[-5:]:  # Show last 5 files
        size = os.path.getsize(f)
        print(f"  {f}: {size:,} bytes")

if __name__ == "__main__":
    asyncio.run(test_single_stream())