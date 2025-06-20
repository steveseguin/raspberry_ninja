#!/usr/bin/env python3
"""
Direct test without subprocess
"""

import asyncio
import sys
import os

sys.path.insert(0, '.')

# Set command line args
sys.argv = [
    'publish.py',
    '--room', 'testroom123',
    '--record', 'direct',
    '--record-room',
    '--password', 'false',
    '--noaudio'
]

async def run_with_timeout():
    from publish import main
    try:
        await asyncio.wait_for(main(), timeout=20)
    except asyncio.TimeoutError:
        print("\nTest completed (timeout)")
    except Exception as e:
        print(f"\nError: {e}")

print("Running direct test...")
asyncio.run(run_with_timeout())