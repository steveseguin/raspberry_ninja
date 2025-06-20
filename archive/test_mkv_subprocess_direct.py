#!/usr/bin/env python3
"""Direct test of MKV subprocess"""
import json
import subprocess
import asyncio
import sys

async def test_mkv_subprocess():
    config = {
        'stream_id': 'test_direct',
        'mode': 'record',
        'room': 'testroom123999999999',
        'record_audio': True,
        'stun_server': 'stun://stun.cloudflare.com:3478'
    }
    
    print("🚀 Starting MKV subprocess directly...")
    
    # Start subprocess
    proc = await asyncio.create_subprocess_exec(
        sys.executable, 'webrtc_subprocess_mkv.py',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    # Send configuration
    proc.stdin.write((json.dumps(config) + '\n').encode())
    await proc.stdin.drain()
    
    # Read initial messages
    for i in range(5):
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=2.0)
            if line:
                msg = json.loads(line.decode())
                print(f"Message: {msg}")
        except asyncio.TimeoutError:
            print("Timeout waiting for message")
            break
        except Exception as e:
            print(f"Error: {e}")
    
    # Send start command
    print("\nSending start command...")
    proc.stdin.write((json.dumps({'type': 'start'}) + '\n').encode())
    await proc.stdin.drain()
    
    # Read more messages
    for i in range(5):
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=2.0)
            if line:
                msg = json.loads(line.decode())
                print(f"Message: {msg}")
        except asyncio.TimeoutError:
            print("No more messages")
            break
        except Exception as e:
            print(f"Error: {e}")
    
    # Check stderr
    stderr_data = await proc.stderr.read()
    if stderr_data:
        print(f"\nSTDERR:\n{stderr_data.decode()}")
    
    # Cleanup
    proc.terminate()
    await proc.wait()
    print("\nTest completed")

if __name__ == "__main__":
    asyncio.run(test_mkv_subprocess())