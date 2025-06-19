#!/usr/bin/env python3
"""
Final integrated test with better error handling
"""

import asyncio
import sys
import os
import glob

# Clean up
for f in glob.glob("final_*.ts") + glob.glob("final_*.mkv"):
    try:
        os.remove(f)
    except:
        pass

sys.path.insert(0, '.')

async def test():
    print("="*60)
    print("FINAL INTEGRATED ROOM RECORDING TEST")
    print("="*60)
    
    # Set args
    sys.argv = [
        'publish.py',
        '--room', 'testroom123',
        '--record', 'final',
        '--record-room',
        '--password', 'false',
        '--noaudio'
    ]
    
    try:
        from publish import main
        
        # Run with timeout
        print("\nStarting room recording...")
        print("Room: testroom123")
        print("Expected stream: KLvZZdT")
        print()
        
        # Run main with timeout
        await asyncio.wait_for(main(), timeout=30)
        
    except asyncio.TimeoutError:
        print("\nTest completed (30s timeout)")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    
    # Check results
    print("\n" + "="*60)
    print("RESULTS:")
    print("="*60)
    
    files = glob.glob("final_*.ts") + glob.glob("final_*.mkv")
    if files:
        print(f"\n✅ SUCCESS! Found {len(files)} recordings:")
        for f in files:
            size = os.path.getsize(f)
            print(f"  {f}: {size:,} bytes")
            
        # Validate
        try:
            from validate_media_file import validate_recording
            print("\nValidating...")
            for f in files:
                result = validate_recording(f, verbose=False)
                print(f"  {f}: {'✅ Valid' if result else '❌ Invalid'}")
        except:
            pass
    else:
        print("\n❌ No recordings found")
        print("\nDebugging hints:")
        print("1. Check if room has active streams")
        print("2. Verify WebRTC negotiation completed")
        print("3. Check ICE connectivity")
        print("4. Look for ERROR messages in output")

# Run
asyncio.run(test())