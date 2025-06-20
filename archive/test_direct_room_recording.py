#!/usr/bin/env python3
"""
Direct test of room recording without subprocess
"""

import asyncio
import sys
import os
import glob

# Clean up
for f in glob.glob("myprefix_*.ts") + glob.glob("myprefix_*.mkv"):
    try:
        os.remove(f)
    except:
        pass

# Import and run directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_room_recording():
    """Test room recording directly"""
    print("="*60)
    print("DIRECT ROOM RECORDING TEST")
    print("Testing with real room: testroom123")
    print("="*60)
    
    # Simulate command line args
    sys.argv = [
        'publish.py',
        '--room', 'testroom123',
        '--record', 'myprefix',
        '--record-room',
        '--password', 'false',
        '--noaudio'
    ]
    
    # Import main
    from publish import main
    
    try:
        # Run for 20 seconds then stop
        main_task = asyncio.create_task(main())
        
        # Wait 20 seconds
        await asyncio.sleep(20)
        
        # Cancel the main task
        main_task.cancel()
        try:
            await main_task
        except asyncio.CancelledError:
            pass
            
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    
    # Check for recordings
    print("\n" + "="*60)
    print("CHECKING FOR RECORDINGS...")
    
    recordings = glob.glob("myprefix_*.ts") + glob.glob("myprefix_*.mkv") + \
                 glob.glob("testroom123_*.ts") + glob.glob("testroom123_*.mkv")
    
    if recordings:
        print(f"\n✅ Found {len(recordings)} recordings:")
        for f in recordings:
            size = os.path.getsize(f)
            print(f"  - {f}: {size:,} bytes")
    else:
        print("\n❌ No recordings found")

# Run the test
if __name__ == "__main__":
    print("Running direct test...")
    asyncio.run(test_room_recording())