#!/usr/bin/env python3
"""Test the HLS subprocess directly"""
import json
import subprocess
import asyncio

async def test_hls_subprocess():
    config = {
        'stream_id': 'test123',
        'mode': 'view',
        'room': 'testroom',
        'use_hls': True,
        'use_splitmuxsink': True,
        'record_audio': True
    }
    
    # Start subprocess
    proc = await asyncio.create_subprocess_exec(
        'python3', 'webrtc_subprocess_hls.py',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    # Send config
    proc.stdin.write((json.dumps(config) + '\n').encode())
    await proc.stdin.drain()
    
    # Read initial response
    try:
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
        msg = json.loads(line.decode())
        print(f"Got response: {msg}")
        
        # Send start command
        proc.stdin.write((json.dumps({'type': 'start'}) + '\n').encode())
        await proc.stdin.drain()
        
        # Read responses for a few seconds
        for i in range(10):
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
                if line:
                    msg = json.loads(line.decode())
                    print(f"Message {i}: {msg}")
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                print(f"Error reading: {e}")
                
    except asyncio.TimeoutError:
        print("Timeout reading from subprocess")
        
    # Check stderr
    stderr = await proc.stderr.read()
    if stderr:
        print(f"STDERR: {stderr.decode()}")
        
    # Terminate
    proc.terminate()
    await proc.wait()

if __name__ == "__main__":
    asyncio.run(test_hls_subprocess())