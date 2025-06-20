#!/usr/bin/env python3
"""Publish a test stream to the room"""

import asyncio
import sys

async def publish_test_stream():
    """Publish a test pattern to the room"""
    print("Publishing test stream to room...")
    
    # Publish a test pattern
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--streamid', 'test_publisher',
        '--test',  # Use test pattern
        '--password', 'false',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    print("Publisher started, waiting for connection...\n")
    
    start_time = asyncio.get_event_loop().time()
    connected = False
    
    while asyncio.get_event_loop().time() - start_time < 30:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
            if line:
                decoded = line.decode().strip()
                if "ready to publish" in decoded.lower() or "pipeline running" in decoded.lower():
                    connected = True
                    print("✓ Publisher connected and streaming!")
                    break
                elif any(word in decoded for word in ["connected", "CONNECTED", "publishing"]):
                    print(f"Status: {decoded}")
        except asyncio.TimeoutError:
            pass
    
    if connected:
        print("\nPublisher is running. Stream ID: test_publisher")
        print("Keep this running and run the recording test in another terminal.")
        print("Press Ctrl+C to stop...")
        
        # Keep running
        try:
            await process.wait()
        except KeyboardInterrupt:
            print("\nStopping publisher...")
            process.terminate()
            await process.wait()
    else:
        print("\nFailed to connect publisher")
        process.terminate()
        await process.wait()

if __name__ == "__main__":
    try:
        asyncio.run(publish_test_stream())
    except KeyboardInterrupt:
        print("\nStopped")