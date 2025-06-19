#!/usr/bin/env python3
"""Test subprocess room recording"""

import asyncio
import subprocess
import sys

async def test_room_recording():
    """Test room recording with subprocess architecture"""
    print("Starting room recording test...")
    
    # Run publish.py with room recording
    cmd = [
        sys.executable, 
        "publish.py",
        "--room", "testroom123",
        "--record-room",
        "--password", "false",
        "--noaudio",
        "--debug"
    ]
    
    # Start the process
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    # Read output for 20 seconds
    start_time = asyncio.get_event_loop().time()
    
    while asyncio.get_event_loop().time() - start_time < 20:
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=0.1)
            if not line:
                break
            
            text = line.decode().strip()
            # Show all output for debugging
            print(text)
                
        except asyncio.TimeoutError:
            continue
    
    # Stop the process
    proc.terminate()
    await proc.wait()
    
    print("Test completed")

if __name__ == "__main__":
    asyncio.run(test_room_recording())