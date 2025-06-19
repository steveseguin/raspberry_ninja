#!/usr/bin/env python3
"""
Final test of room recording
"""

import asyncio
import sys
import os
import glob
import time

# Clean up
for pattern in ["myprefix_*.ts", "myprefix_*.mkv", "testroom123_*.ts", "testroom123_*.mkv"]:
    for f in glob.glob(pattern):
        try:
            os.remove(f)
        except:
            pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_room_recording():
    """Final test with proper setup"""
    print("="*70)
    print("FINAL ROOM RECORDING TEST")
    print("Room: testroom123 (has stream KLvZZdT)")
    print("="*70)
    
    # Import after path setup
    from publish import main
    import argparse
    
    # Set up args properly
    sys.argv = [
        'publish.py',
        '--room', 'testroom123',
        '--record', 'myprefix',  
        '--record-room',
        '--password', 'false',
        '--noaudio'
    ]
    
    # Parse args like main() does
    parser = argparse.ArgumentParser()
    
    # Add all the arguments
    parser.add_argument('--room', type=str, help='Room name to join')
    parser.add_argument('--record', type=str, help='Record prefix')
    parser.add_argument('--record-room', action='store_true', help='Record all streams in room')
    parser.add_argument('--password', type=str, help='Room password')
    parser.add_argument('--noaudio', action='store_true', help='Disable audio')
    parser.add_argument('--novideo', action='store_true')
    parser.add_argument('--server', type=str)
    parser.add_argument('--hostname', type=str)
    parser.add_argument('--streamid', type=str)
    parser.add_argument('--bitrate', type=int, default=2500)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    parser.add_argument('--framerate', type=int, default=30)
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--h264', action='store_true')
    parser.add_argument('--vp8', action='store_true')
    parser.add_argument('--vp9', action='store_true')
    parser.add_argument('--av1', action='store_true')
    parser.add_argument('--pipein', type=str)
    parser.add_argument('--filesrc', type=str)
    parser.add_argument('--ndiout', type=str)
    parser.add_argument('--midi', type=str)
    parser.add_argument('--save', type=str)
    parser.add_argument('--rotate', type=int, default=0)
    parser.add_argument('--buffer', type=int, default=200)
    parser.add_argument('--pipeline', type=str)
    parser.add_argument('--room-ndi', action='store_true')
    parser.add_argument('--fdsink', action='store_true')
    parser.add_argument('--framebuffer', action='store_true')
    parser.add_argument('--socketout', action='store_true')
    parser.add_argument('--socketport', type=int)
    parser.add_argument('--multiviewer', action='store_true')
    parser.add_argument('--aom', action='store_true')
    parser.add_argument('--view', action='store_true')
    parser.add_argument('--nored', action='store_true')
    parser.add_argument('--noqos', action='store_true')
    parser.add_argument('--zerolatency', action='store_true')
    parser.add_argument('--noprompt', action='store_true')
    
    args = parser.parse_args()
    
    # Debug args
    print(f"\nParsed args:")
    print(f"  record: {args.record}")
    print(f"  record_room: {args.record_room}")
    print(f"  room: {args.room}")
    
    # Run main
    print("\nStarting room recording...")
    main_task = asyncio.create_task(main())
    
    # Monitor for 30 seconds
    start_time = time.time()
    await asyncio.sleep(30)
    
    print(f"\nStopping after {int(time.time() - start_time)} seconds...")
    main_task.cancel()
    try:
        await main_task
    except asyncio.CancelledError:
        pass
    
    # Give it time to clean up
    await asyncio.sleep(2)
    
    # Check results
    print("\n" + "="*70)
    print("RESULTS:")
    print("="*70)
    
    files = []
    for pattern in ["myprefix_*.ts", "myprefix_*.mkv", "testroom123_*.ts", "testroom123_*.mkv"]:
        files.extend(glob.glob(pattern))
    
    if files:
        print(f"\n✅ SUCCESS! Found {len(files)} recordings:")
        for f in files:
            size = os.path.getsize(f)
            print(f"  {f}: {size:,} bytes")
            
        # Validate
        try:
            from validate_media_file import validate_recording
            print("\nValidating recordings...")
            for f in files:
                result = validate_recording(f, verbose=False)
                print(f"  {f}: {'✅ Valid' if result else '❌ Invalid'}")
        except Exception as e:
            print(f"\nValidation error: {e}")
    else:
        print("\n❌ FAILED - No recordings found")
        print("\nDebugging hints:")
        print("1. Check if multi_peer_client was created")
        print("2. Verify WebRTC negotiation completed") 
        print("3. Check ICE connectivity")
        print("4. Ensure pipeline setup succeeded")
    
    return len(files) > 0

if __name__ == "__main__":
    try:
        success = asyncio.run(test_room_recording())
        print(f"\n{'='*70}")
        print(f"TEST {'PASSED' if success else 'FAILED'}")
        print(f"{'='*70}")
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()