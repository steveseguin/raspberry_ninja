#!/usr/bin/env python3
"""
Direct test of integrated room recording
"""

import asyncio
import sys
import os
import glob
import time

# Clean up
for f in glob.glob("direct_*.ts") + glob.glob("direct_*.mkv"):
    try:
        os.remove(f)
    except:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set args
sys.argv = [
    'publish.py',
    '--room', 'testroom123',
    '--record', 'direct',
    '--record-room',
    '--password', 'false',
    '--noaudio'
]

async def test_with_timeout():
    """Run main with timeout"""
    from publish import main
    
    # Create main task
    main_task = asyncio.create_task(main())
    
    # Run for 30 seconds
    await asyncio.sleep(30)
    
    # Cancel
    main_task.cancel()
    try:
        await main_task
    except asyncio.CancelledError:
        pass

print("="*60)
print("DIRECT INTEGRATED TEST")
print("="*60)

# Run test
try:
    asyncio.run(test_with_timeout())
except Exception as e:
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()

# Check results
print("\n" + "="*60)
print("RESULTS:")

files = glob.glob("direct_*.ts") + glob.glob("direct_*.mkv")
if files:
    print(f"\n✅ Found {len(files)} recordings:")
    for f in files:
        print(f"  {f}: {os.path.getsize(f):,} bytes")
else:
    print("\n❌ No recordings found")